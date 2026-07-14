"""Context management utilities for storing request-scoped data."""

from __future__ import annotations

from contextvars import ContextVar

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Context variables for storing request-scoped data
AUTH_TOKEN_KEY = "auth_token"
TENANT_ID_KEY = "tenant_id"
COMPANY_ID_KEY = "company_id"  # For compatibility

_auth_token_var: ContextVar[str | None] = ContextVar(AUTH_TOKEN_KEY, default=None)
_tenant_id_var: ContextVar[str | None] = ContextVar(TENANT_ID_KEY, default=None)
_company_id_var: ContextVar[str | None] = ContextVar(COMPANY_ID_KEY, default=None)


def _oidc_session_token() -> str | None:
    """Return the per-user access token from an active OIDCProxy session, if any.

    In remote/HTTP mode the browser login flow makes the user's token available
    via FastMCP's request-scoped dependency. Outside a request (e.g. stdio mode)
    this quietly returns ``None`` so the other resolution strategies apply.
    """
    try:
        from fastmcp.server.dependencies import get_access_token

        access = get_access_token()
        token = getattr(access, "token", None) if access is not None else None
        return token or None
    except Exception:
        return None


def get_auth_token() -> str | None:
    """Resolve the authentication token for outbound m8flow API calls.

    Resolution order:
      1. OIDCProxy per-user session token (remote/browser login).
      2. Explicit bearer token set at startup (env / settings).
      3. ROPC token auto-fetched (and refreshed) from Keycloak using
         KEYCLOAK_USERNAME / KEYCLOAK_PASSWORD.

    Returns:
        A usable access token, or None if none can be resolved.
    """
    # 1. Per-user token from a browser (OIDCProxy) session.
    session_token = _oidc_session_token()
    if session_token:
        return session_token

    # 2. Explicit bearer token captured at startup.
    static_token = _auth_token_var.get()
    if static_token:
        return static_token

    # 3. ROPC auto-login (lazy import avoids an import cycle at module load).
    from src.config import settings

    if settings.has_ropc_credentials:
        try:
            from src.auth.token_service import token_service

            return token_service.get_token_sync()
        except RuntimeError as exc:
            logger.warning("ROPC token acquisition failed: %s", exc)

    return None


def set_auth_token(token: str) -> None:
    """Set authentication token in context.

    Args:
        token: Authentication token to set.
    """
    _auth_token_var.set(token)


def get_tenant_id() -> str | None:
    """Get tenant ID from context.

    Returns:
        Tenant ID or None if not set.
    """
    return _tenant_id_var.get()


def set_tenant_id(tenant_id: str) -> None:
    """Set tenant ID in context.

    Args:
        tenant_id: Tenant ID to set.
    """
    _tenant_id_var.set(tenant_id)


def get_company_id_safe() -> str | None:
    """Get company ID from context (alias for tenant_id for compatibility).

    Returns:
        Company/Tenant ID or None if not set.
    """
    return _company_id_var.get() or get_tenant_id()


def set_company_id(company_id: str) -> None:
    """Set company ID in context.

    Args:
        company_id: Company ID to set.
    """
    _company_id_var.set(company_id)


def clear_context() -> None:
    """Clear all context variables."""
    _auth_token_var.set(None)
    _tenant_id_var.set(None)
    _company_id_var.set(None)
