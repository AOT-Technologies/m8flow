"""Main entry point for m8flow MCP server."""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys

from fastmcp import FastMCP
from starlette.responses import JSONResponse

from src.auth.jwt_utils import TENANT_ID_CLAIM, decode_jwt_claims
from src.client.http_client import shutdown_http_client
from src.config import settings
from src.mcp_tools import register_tools
from src.middleware import (
    ContextExtractionMiddleware,
    ObservabilityMiddleware,
    TenantContextMiddleware,
)
from src.utils.context import set_auth_token, set_tenant_id
from src.utils.logging import get_logger, setup_logging

# Setup logging
setup_logging()
logger = get_logger(__name__)


def _build_auth() -> object | None:
    """Build an OIDCProxy for browser-based Keycloak login (remote mode only).

    Returns None when browser login is not applicable (stdio mode, or no
    confidential Keycloak client configured), leaving token resolution to the
    static-bearer / ROPC strategies in ``get_auth_token``.
    """
    if not (settings.is_remote and settings.has_oidc_client):
        return None
    try:
        from fastmcp.server.auth.oidc_proxy import OIDCProxy
    except Exception as exc:  # pragma: no cover - depends on fastmcp version
        logger.warning("OIDCProxy unavailable (%s); falling back to token-based auth", exc)
        return None

    config_url = settings.oidc_config_url or settings.keycloak_well_known_url
    logger.info(
        "Browser login enabled (OIDCProxy): base=%s issuer=%s config=%s",
        settings.oidc_base_url,
        settings.oidc_issuer_url,
        config_url,
    )
    try:
        # fastmcp fetches the OIDC discovery document here, so an unreachable
        # Keycloak raises at construction time. Fail gracefully instead of
        # crash-looping the container; token-based auth still works.
        return OIDCProxy(
            config_url=config_url,
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            base_url=settings.oidc_base_url,
            issuer_url=settings.oidc_issuer_url,
            required_scopes=settings.required_scopes_list,
            verify_id_token=settings.verify_id_token,
            require_authorization_consent=settings.mcp_oidc_require_consent,
            redirect_path=settings.mcp_oidc_redirect_path,
        )
    except Exception as exc:
        logger.error(
            "Could not initialize browser login — Keycloak discovery unreachable at %s (%s). "
            "Is KEYCLOAK_URL reachable from this process? In Docker, 'localhost' is the "
            "container, not the host: use http://host.docker.internal:6842 or the Keycloak "
            "service name. Continuing with token-based auth (bearer / ROPC).",
            config_url,
            exc,
        )
        return None


# Create FastMCP server (with browser login when configured for remote mode)
_auth = _build_auth()
mcp = FastMCP("m8flow", auth=_auth) if _auth is not None else FastMCP("m8flow")

# Add middleware (order matters: observability wraps everything)
mcp.add_middleware(ObservabilityMiddleware())
mcp.add_middleware(ContextExtractionMiddleware())
mcp.add_middleware(TenantContextMiddleware())


def _configure_static_token() -> None:
    """Capture an explicit bearer token (if provided) for token resolution.

    When absent, ``get_auth_token`` falls back to OIDCProxy session tokens
    (remote) or ROPC auto-login (KEYCLOAK_USERNAME / KEYCLOAK_PASSWORD).
    """
    auth_token = os.getenv("M8FLOW_BEARER_TOKEN") or os.getenv("FORMSFLOW_BEARER_TOKEN") or settings.m8flow_bearer_token

    if not auth_token:
        if _auth is not None:
            logger.info("No static token set; users authenticate via browser (OIDCProxy)")
        elif settings.has_ropc_credentials:
            logger.info("No static token set; using ROPC auto-login (KEYCLOAK_USERNAME/PASSWORD)")
        else:
            logger.warning(
                "No authentication configured — set M8FLOW_BEARER_TOKEN, "
                "KEYCLOAK_USERNAME/PASSWORD (ROPC), or a Keycloak client for browser login"
            )
        return

    if not auth_token.startswith("Bearer "):
        auth_token = f"Bearer {auth_token}"
    set_auth_token(auth_token)

    claims = decode_jwt_claims(auth_token)
    tenant_id = claims.get(TENANT_ID_CLAIM)
    if tenant_id:
        set_tenant_id(tenant_id)
        logger.info(
            "Authentication configured: user=%s, tenant=%s...",
            claims.get("preferred_username"),
            str(tenant_id)[:20],
        )
    else:
        logger.warning("No %s found in JWT claims", TENANT_ID_CLAIM)

    logger.info("Static auth token configured (length: %d chars)", len(auth_token))


_configure_static_token()

# Register all tools
register_tools(mcp)

logger.info("m8flow MCP server initialized in %s mode", settings.server_type)


def _oauth_protected_resource_document() -> dict:
    return {
        "resource": settings.oidc_base_url,
        "authorization_servers": [settings.oidc_issuer_url],
        "bearer_methods_supported": ["header"],
    }


def _oauth_authorization_server_document() -> dict:
    issuer = settings.oidc_issuer_url
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "registration_endpoint": f"{issuer}/register",
        "revocation_endpoint": f"{issuer}/revoke",
        "scopes_supported": settings.required_scopes_list,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
    }


def _register_http_routes(server: object) -> None:
    """Add health-check and OAuth discovery routes to the streamable-HTTP app."""

    async def health_check(request):  # noqa: ANN001, ARG001
        return JSONResponse({"status": "healthy", "server": "m8flow-mcp", "version": "1.0.0"})

    async def protected_resource(request):  # noqa: ANN001, ARG001
        return JSONResponse(_oauth_protected_resource_document())

    async def authorization_server(request):  # noqa: ANN001, ARG001
        return JSONResponse(_oauth_authorization_server_document())

    server.add_route("/health", health_check, methods=["GET"])
    server.add_route("/mcp/health", health_check, methods=["GET"])

    # RFC 9728 discovery documents (root + /mcp-protocol aliases for Cursor/Claude).
    server.add_route("/.well-known/oauth-protected-resource", protected_resource, methods=["GET"])
    server.add_route("/.well-known/oauth-protected-resource/mcp-protocol", protected_resource, methods=["GET"])
    server.add_route("/.well-known/oauth-authorization-server", authorization_server, methods=["GET"])
    server.add_route(
        "/.well-known/oauth-authorization-server/mcp-protocol",
        authorization_server,
        methods=["GET"],
    )


def _install_shutdown_hook(server: object) -> None:
    """Ensure the shared HTTP client is closed when the ASGI app shuts down.

    FastMCP's http_app is driven by a lifespan context manager (no
    add_event_handler / on_shutdown support), so we wrap the existing lifespan
    rather than replace it.
    """
    original_lifespan = server.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan_with_cleanup(app):  # noqa: ANN001, ANN202
        async with original_lifespan(app):
            try:
                yield
            finally:
                await shutdown_http_client()

    server.router.lifespan_context = lifespan_with_cleanup


def main() -> int:
    """Run the MCP server.

    Returns:
        Exit code
    """
    try:
        if settings.is_remote:
            # HTTP mode for Cursor / streamable-http clients
            logger.info("Starting m8flow MCP server in HTTP mode on %s:%s", settings.host, settings.port)

            server = mcp.http_app(transport="streamable-http")
            _register_http_routes(server)
            _install_shutdown_hook(server)
            logger.info("Health + OAuth discovery endpoints registered")

            import uvicorn

            uvicorn.run(server, host=settings.host, port=settings.port, log_level="info")
        else:
            # stdio mode for Claude Desktop
            logger.info("Starting m8flow MCP server in stdio mode")
            try:
                mcp.run(transport="stdio")
            finally:
                # Best-effort cleanup of the shared HTTP client on exit.
                with contextlib.suppress(Exception):
                    asyncio.run(shutdown_http_client())

        return 0

    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0

    except Exception as e:
        logger.error("Server error: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
