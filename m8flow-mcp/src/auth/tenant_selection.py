"""Multi-tenant selection for the m8flow MCP server.

Shared building blocks used by both transports (remote OIDC and stdio) to let a
multi-tenant user pick a tenant during MCP authentication and to authenticate that
tenant the **same way the web app does** — by driving the backend tenant-finalization
endpoint (``/v1.0/login?...tenant=<alias>&tenant_finalization=1``).

This module intentionally contains no fastmcp / transport specifics so it can be
reused by ``oidc_tenant_proxy`` (remote) and ``stdio_tenant_login`` (stdio).
"""

from __future__ import annotations

import asyncio
import html as html_lib
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from src.auth.jwt_utils import decode_jwt_claims
from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

ORGANIZATION_CLAIM = "organization"

# Cookie name the backend Set-Cookies on tenant finalization to carry the selected tenant
# id (m8flow-backend ``tenancy.SELECTED_TENANT_COOKIE_NAME``); read from the finalization
# response to learn the canonical tenant id.
SELECTED_TENANT_COOKIE_NAME = "m8flow_selected_tenant"


def _clean_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _membership(alias: str, details: Mapping[str, Any]) -> dict[str, str | None]:
    return {
        "alias": alias,
        "id": _clean_str(details.get("id")),
        "name": _clean_str(details.get("name")),
    }


def organization_memberships(token: str | Mapping[str, Any] | None) -> list[dict[str, str | None]]:
    """Return ``[{alias, id, name}]`` from a token's ``organization`` claim.

    Mirrors the backend ``organization_memberships_from_payload`` normalization so the
    MCP lists exactly the tenants the web app would list. Accepts a raw/bearer token
    string or an already-decoded claims mapping.
    """
    if token is None:
        return []
    claims = token if isinstance(token, Mapping) else decode_jwt_claims(token)

    organization_claim = claims.get(ORGANIZATION_CLAIM)
    memberships: list[dict[str, str | None]] = []

    if isinstance(organization_claim, Mapping):
        for alias, details in organization_claim.items():
            alias_str = _clean_str(alias)
            if alias_str and isinstance(details, Mapping):
                memberships.append(_membership(alias_str, details))
    elif isinstance(organization_claim, list):
        for item in organization_claim:
            if isinstance(item, str):
                alias_str = _clean_str(item)
                if alias_str:
                    memberships.append({"alias": alias_str, "id": None, "name": None})
            elif isinstance(item, Mapping):
                alias_str = _clean_str(item.get("alias"))
                if alias_str:
                    memberships.append(_membership(alias_str, item))

    return memberships


def subject_from_token(token: str | None) -> str | None:
    """Return the ``sub`` claim used to key a user's tenant selection."""
    if not token:
        return None
    return _clean_str(decode_jwt_claims(token).get("sub"))


def _raw_token(token: str) -> str:
    return token[7:] if token.startswith("Bearer ") else token


# Refresh a finalized token this many seconds before it actually expires.
_TOKEN_REFRESH_MARGIN_SECONDS = 60


@dataclass
class FinalizedSession:
    """A finalized tenant session — the tenant-scoped token the backend issued.

    ``access_token`` is the Spiff-internal, tenant-scoped JWT returned by the backend
    tenant-finalization endpoint (carrying ``m8flow_tenant_id`` + the active org's
    groups). It is what the MCP forwards to the backend on every subsequent call, exactly
    as the web app forwards its session cookie.
    """

    alias: str
    tenant_id: str
    access_token: str
    expires_at: float

    @property
    def is_fresh(self) -> bool:
        return time.time() < (self.expires_at - _TOKEN_REFRESH_MARGIN_SECONDS)


async def finalize_tenant(shared_realm_token: str, alias: str) -> FinalizedSession | None:
    """Authenticate a tenant by driving the backend tenant-finalization endpoint.

    This is the exact flow the web app uses (``TenantSelectPage`` →
    ``/v1.0/login?...tenant=<alias>&tenant_finalization=1``): the backend fetches the
    selected organization's groups from Keycloak, synchronizes local RBAC for the tenant,
    issues a **tenant-scoped access token**, and sets the ``m8flow_selected_tenant``
    cookie. No new logic and no backend change — we present the shared-realm token as the
    ``access_token`` cookie and capture the tenant-scoped token from the response.

    Returns a ``FinalizedSession`` on success, or ``None`` when the user is not a member
    or the call fails.
    """
    identifier = settings.effective_shared_realm_identifier
    url = f"{settings.m8flow_api_url.rstrip('/')}/v1.0/login"
    params = {
        "authentication_identifier": identifier,
        "tenant": alias,
        "tenant_finalization": "1",
        # Relative path — accepted by the backend's frontend-redirect allowlist.
        "redirect_url": "/",
    }
    cookies = {
        "access_token": _raw_token(shared_realm_token),
        "authentication_identifier": identifier,
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.m8flow_api_timeout,
            follow_redirects=False,
        ) as client:
            response = await client.get(url, params=params, cookies=cookies)
    except httpx.HTTPError as exc:
        logger.warning("Tenant finalization request failed for alias=%s: %s", alias, exc)
        return None

    # Success is a redirect (302). A 4xx means the tenant is not available for this user.
    if response.status_code >= 400:
        logger.warning(
            "Tenant finalization returned %s for alias=%s (user may not be a member)",
            response.status_code,
            alias,
        )
        return None

    enriched_token = response.cookies.get("access_token")
    tenant_id = response.cookies.get(SELECTED_TENANT_COOKIE_NAME)
    if not enriched_token or not tenant_id:
        # The finalization branch did not run (e.g. token not parseable as shared-realm);
        # without the tenant-scoped token we cannot fix RBAC, so treat as failure.
        logger.warning("Tenant finalization for alias=%s did not return a tenant-scoped token/cookie", alias)
        return None

    exp = decode_jwt_claims(enriched_token).get("exp")
    expires_at = float(exp) if isinstance(exp, (int, float)) else (time.time() + 900)

    logger.info("Tenant finalized for alias=%s -> tenant_id=%s", alias, tenant_id)
    return FinalizedSession(
        alias=alias,
        tenant_id=str(tenant_id),
        access_token=enriched_token,
        expires_at=expires_at,
    )


async def refresh_if_needed(session: FinalizedSession, shared_realm_token: str) -> FinalizedSession | None:
    """Return the session if its tenant-scoped token is still fresh, else re-finalize.

    The tenant-scoped token expires (~1 day). When it is near expiry we re-run the
    finalization with the current shared-realm session token to mint a fresh one (also
    re-syncing RBAC, idempotently).
    """
    if session.is_fresh:
        return session
    return await finalize_tenant(shared_realm_token, session.alias)


class TenantSelectionStore:
    """Process-local store of finalized tenant sessions, keyed by user ``sub``.

    The MCP server runs as a single process (single uvicorn worker in remote mode; one
    process in stdio mode), so an in-memory store is sufficient and avoids extra
    infrastructure. Keyed by the shared-realm session token's ``sub`` (stable across
    requests) — never by the tenant-scoped token's ``sub``, which differs.
    """

    def __init__(self) -> None:
        self._by_subject: dict[str, FinalizedSession] = {}
        self._lock = asyncio.Lock()

    async def set(self, subject: str, session: FinalizedSession) -> None:
        async with self._lock:
            self._by_subject[subject] = session

    async def get(self, subject: str | None) -> FinalizedSession | None:
        if not subject:
            return None
        async with self._lock:
            return self._by_subject.get(subject)


# Module-level singleton shared by the proxy (writer) and the request middleware (reader).
selection_store = TenantSelectionStore()


# ---------------------------------------------------------------------------
# stdio: single-process selection
# ---------------------------------------------------------------------------
# stdio serves a single user in one process, so its selection is a plain module global
# (the async, per-``sub`` store above is only meaningful for the multi-session remote
# transport). Set once at startup by the stdio picker; read by the request middleware.
_process_selected_session: FinalizedSession | None = None


def set_process_selected_session(session: FinalizedSession | None) -> None:
    """Record the finalized tenant session selected for this stdio process."""
    global _process_selected_session
    _process_selected_session = session


def get_process_selected_session() -> FinalizedSession | None:
    """Return the finalized tenant session selected for this stdio process, if any."""
    return _process_selected_session


def render_selection_page(
    memberships: list[dict[str, str | None]],
    *,
    action: str,
    method: str = "post",
    hidden_fields: dict[str, str] | None = None,
    title: str = "Select a tenant",
    description: str = "Your account belongs to multiple tenants. Choose one to continue.",
) -> str:
    """Render a self-contained tenant-selection HTML page.

    Each tenant is a submit button posting ``tenant=<alias>`` to ``action`` (styled to
    match the web app's ``TenantSelectPage``). ``hidden_fields`` carries flow binding
    (e.g. a signed state) for the remote transport.
    """
    hidden_html = "".join(
        f'<input type="hidden" name="{html_lib.escape(name)}" value="{html_lib.escape(value)}">'
        for name, value in (hidden_fields or {}).items()
    )

    buttons = "".join(
        (
            f'<button class="tenant" type="submit" name="tenant" '
            f'value="{html_lib.escape(m["alias"] or "")}">'
            f'<span class="tenant-name">{html_lib.escape(m["name"] or m["alias"] or "")}</span>'
            f'<span class="tenant-alias">{html_lib.escape(m["alias"] or "")}</span>'
            f"</button>"
        )
        for m in memberships
        if m.get("alias")
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>{html_lib.escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
         min-height: 100vh; display: flex; align-items: center; justify-content: center;
         background: #f5f6f8; color: #1a1a1a; }}
  @media (prefers-color-scheme: dark) {{ body {{ background: #16181d; color: #f1f1f1; }} }}
  .card {{ width: min(28rem, 92vw); padding: 2rem; border-radius: 12px; background: #fff;
          box-shadow: 0 6px 24px rgba(0,0,0,.12); }}
  @media (prefers-color-scheme: dark) {{ .card {{ background: #22252c; box-shadow: none;
          border: 1px solid #33373f; }} }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .5rem; }}
  p {{ margin: 0 0 1.25rem; color: #555; }}
  @media (prefers-color-scheme: dark) {{ p {{ color: #b5b9c2; }} }}
  form {{ display: flex; flex-direction: column; gap: .625rem; }}
  button.tenant {{ display: flex; justify-content: space-between; align-items: center;
          padding: .875rem 1rem; border: 1px solid #d3d6dd; border-radius: 8px;
          background: #fff; cursor: pointer; font-size: 1rem; text-align: left; }}
  button.tenant:hover {{ border-color: #2f6fed; background: #f2f6ff; }}
  @media (prefers-color-scheme: dark) {{ button.tenant {{ background: #2a2e36; color: #f1f1f1;
          border-color: #3a3f49; }} button.tenant:hover {{ border-color: #5b8bff; background: #313743; }} }}
  .tenant-alias {{ color: #888; font-size: .85rem; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{html_lib.escape(title)}</h1>
    <p>{html_lib.escape(description)}</p>
    <form method="{html_lib.escape(method)}" action="{html_lib.escape(action)}">
      {hidden_html}
      {buttons}
    </form>
  </div>
</body>
</html>"""
