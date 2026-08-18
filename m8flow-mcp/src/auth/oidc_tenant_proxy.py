"""OIDC proxy that adds a tenant-selection screen for multi-tenant users (remote mode).

Subclasses fastmcp's ``OIDCProxy`` without modifying vendored fastmcp. It injects a
tenant-selection screen into the OIDC login redirect chain and authenticates the chosen
tenant by driving the backend tenant-finalization endpoint — the same flow the web app
uses (see ``tenant_selection.finalize_tenant``).

Flow:
1. Sign-in requests the ``organization`` scope so the token enumerates the user's orgs.
2. After the IdP callback runs, inspect the just-issued authorization code's upstream
   token. 0/1 org → continue normally (1 org is auto-finalized); >1 org → render the
   selection screen instead of returning to the MCP client.
3. ``POST /select-tenant`` finalizes the chosen tenant, stores the selection keyed by
   the user's ``sub``, then resumes the original client redirect.

The wrapper reads two fastmcp internals read-only (``self._code_store`` and
``ClientCode.idp_tokens``); on any unexpected error it returns the unmodified parent
response so login never breaks.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

from fastmcp.server.auth.oidc_proxy import OIDCProxy
from fastmcp.server.auth.redirect_validation import (
    _has_dot_segments,
    validate_redirect_uri,
)
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from src.auth.tenant_selection import (
    finalize_tenant,
    organization_memberships,
    render_selection_page,
    selection_store,
    subject_from_token,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

_SELECT_TENANT_PATH = "/select-tenant"

# Signed tenant-selection state older than this is rejected, bounding replay of an
# intercepted-but-still-validly-signed state to a short window. Generous enough for a
# human to read the screen and pick a tenant.
_STATE_TTL_SECONDS = 600


class TenantSelectingOIDCProxy(OIDCProxy):
    """OIDCProxy that prompts multi-tenant users to select a tenant during login."""

    # -- routes ---------------------------------------------------------------

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        """Wrap the IdP callback route and add the ``/select-tenant`` route."""
        routes = super().get_routes(mcp_path)
        patched: list[Route] = []
        for route in routes:
            if isinstance(route, Route) and route.path == self._redirect_path:
                patched.append(
                    Route(
                        path=self._redirect_path,
                        endpoint=self._handle_idp_callback_with_tenant_selection,
                        methods=["GET"],
                    )
                )
            else:
                patched.append(route)

        patched.append(
            Route(
                path=_SELECT_TENANT_PATH,
                endpoint=self._handle_select_tenant,
                methods=["GET", "POST"],
            )
        )
        return patched

    # -- callback interception ------------------------------------------------

    async def _handle_idp_callback_with_tenant_selection(self, request: Request) -> HTMLResponse | RedirectResponse:
        """Run the standard callback, then interpose tenant selection when needed."""
        response = await self._handle_idp_callback(request)
        try:
            if not isinstance(response, RedirectResponse):
                return response

            location = response.headers.get("location", "")
            client_code = _query_param(location, "code")
            if not client_code:
                return response

            idp_tokens = await self._idp_tokens_for_client_code(client_code)
            token = _upstream_token(idp_tokens)
            if not token:
                return response

            memberships = organization_memberships(token)
            subject = subject_from_token(token)

            # 0 tenants -> global/master user (no tenant); 1 -> auto-finalize (no screen).
            if len(memberships) <= 1:
                if len(memberships) == 1 and subject:
                    await self._finalize_and_store(token, memberships[0]["alias"], subject)
                return response

            # >1 tenants -> show the selection screen, binding the pending client redirect.
            state = self._encode_state(client_code=client_code, client_redirect=location)
            html = render_selection_page(
                memberships,
                action=self._select_tenant_url(),
                hidden_fields={"state": state},
            )
            return HTMLResponse(content=html)
        except Exception:
            logger.warning(
                "Tenant-selection interception failed; continuing with standard login",
                exc_info=True,
            )
            return response

    async def _handle_select_tenant(self, request: Request) -> HTMLResponse | RedirectResponse:
        """Finalize the chosen tenant and resume the original client redirect."""
        if request.method != "POST":
            return HTMLResponse("<h1>Method Not Allowed</h1>", status_code=405)

        form = await request.form()
        alias = _form_str(form.get("tenant"))
        state = self._decode_state(_form_str(form.get("state")))
        if not alias or state is None:
            return HTMLResponse("<h1>Invalid tenant selection request.</h1>", status_code=400)

        client_code = state.get("client_code")
        client_redirect = state.get("client_redirect")
        if not client_code or not client_redirect:
            return HTMLResponse("<h1>Invalid or expired tenant selection.</h1>", status_code=400)

        # Never emit an unvalidated redirect target: even though the state is signed, the
        # resume URL carries an OAuth code, so it must point at a legitimate MCP-client
        # callback, not an attacker-chosen host.
        if not self._validate_client_redirect(client_redirect):
            logger.warning("Rejected tenant-selection redirect to untrusted target: %s", client_redirect)
            return HTMLResponse("<h1>Invalid redirect target.</h1>", status_code=400)

        idp_tokens = await self._idp_tokens_for_client_code(client_code)
        token = _upstream_token(idp_tokens)
        if not token:
            return HTMLResponse(
                "<h1>Your login session expired. Please authenticate again.</h1>",
                status_code=400,
            )

        memberships = organization_memberships(token)
        if alias not in {m["alias"] for m in memberships}:
            return HTMLResponse(
                "<h1>Selected tenant is not available for your account.</h1>",
                status_code=403,
            )

        subject = subject_from_token(token)
        finalized = await self._finalize_and_store(token, alias, subject)
        if not finalized:
            return HTMLResponse(
                "<h1>Could not activate the selected tenant. Please try again.</h1>",
                status_code=502,
            )

        return RedirectResponse(url=client_redirect, status_code=302)

    # -- helpers --------------------------------------------------------------

    async def _idp_tokens_for_client_code(self, client_code: str) -> dict[str, Any] | None:
        """Read (without consuming) the upstream tokens stored for a client code."""
        code_model = await self._code_store.get(key=client_code)
        if code_model is None:
            return None
        idp_tokens = getattr(code_model, "idp_tokens", None)
        return idp_tokens if isinstance(idp_tokens, dict) else None

    async def _finalize_and_store(self, token: str, alias: str, subject: str | None) -> bool:
        """Finalize a tenant via the backend and remember it for this user's session."""
        finalized = await finalize_tenant(token, alias)
        if finalized is None:
            return False
        if subject:
            await selection_store.set(subject, finalized)
        return True

    def _select_tenant_url(self) -> str:
        return f"{str(self.base_url).rstrip('/')}{_SELECT_TENANT_PATH}"

    def _validate_client_redirect(self, url: str) -> bool:
        """Return True only for a well-formed, trusted MCP-client callback URL.

        Structural floor (always enforced): an absolute ``http(s)`` URL with a host, no
        userinfo (``user:pass@host`` bypasses naive host checks), and no ``.``/``..`` path
        segments (a browser collapses those in a 302 Location and can escape the allowlist).
        When the parent ``OAuthProxy`` was configured with an explicit redirect-URI
        allowlist, the target must also match it; when it is unset (fastmcp's DCR allow-all
        default) the structural floor stands.
        """
        parts = urlsplit(url)
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
            return False
        if parts.username is not None or parts.password is not None:
            return False
        if _has_dot_segments(parts.path):
            return False

        allowed = getattr(self, "_allowed_client_redirect_uris", None)
        if allowed is not None:
            return validate_redirect_uri(url, allowed)
        return True

    def _encode_state(self, *, client_code: str, client_redirect: str) -> str:
        payload = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "client_code": client_code,
                    "client_redirect": client_redirect,
                    "iat": int(time.time()),
                }
            ).encode()
        ).decode()
        return self._sign_cookie(payload)

    def _decode_state(self, signed: str | None) -> dict[str, str] | None:
        if not signed:
            return None
        payload = self._verify_cookie(signed)
        if not payload:
            return None
        try:
            data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        # Reject stale (but still validly signed) state to bound replay.
        iat = data.get("iat")
        if not isinstance(iat, (int, float)) or (time.time() - iat) > _STATE_TTL_SECONDS:
            return None
        client_code = data.get("client_code")
        client_redirect = data.get("client_redirect")
        if isinstance(client_code, str) and isinstance(client_redirect, str):
            return {"client_code": client_code, "client_redirect": client_redirect}
        return None


def _query_param(url: str, name: str) -> str | None:
    try:
        values = parse_qs(urlsplit(url).query).get(name)
    except Exception:
        return None
    return values[0] if values else None


def _upstream_token(idp_tokens: dict[str, Any] | None) -> str | None:
    if not isinstance(idp_tokens, dict):
        return None
    token = idp_tokens.get("access_token") or idp_tokens.get("id_token")
    return token if isinstance(token, str) and token else None


def _form_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None
