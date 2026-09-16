# m8flow-backend/src/m8flow_backend/routes/login_controller.py
"""Browser-redirect Keycloak login/logout.

`POST /v1.0/login` (routes/v1.py) is a JSON credentials endpoint that mints an
internal token directly — it does not talk to Keycloak. This module is the
other kind of login: the one a browser hits by full-page redirect.

  1. `GET /v1.0/login` sends the browser to Keycloak's hosted login page.
  2. Keycloak redirects back to `GET /v1.0/login_return` with an authorization
     code.
  3. This exchanges the code for tokens (server-side, using the confidential
     `m8flow-backend` Keycloak client) and sets `access_token`/`id_token`/
     `refresh_token` cookies, then redirects to the caller's original
     `redirect_url`.
  4. `POST /v1.0/refresh` silently mints a fresh `access_token`/`id_token`
     from the `refresh_token` cookie. m8flow-frontend's HttpService tries this
     first on a 401 before falling back to a full `GET /v1.0/login` redirect —
     see HttpService.ts. Without it, every access-token expiry (30 min of
     idle) forced a full round trip through Keycloak's `/auth` endpoint, which
     is where a known Keycloak quirk (a still-live AUTH_SESSION_ID/KC_RESTART
     cookie pointing at an already-evicted server-side auth session) can
     surface as Keycloak's own "loginTimeout" error page.
  5. `GET /v1.0/logout` clears those cookies and ends the Keycloak SSO session.

This gap was later filled by this module.
"""
from __future__ import annotations

import ast
import base64
import logging
import secrets
from urllib.parse import unquote

from flask import Response, jsonify, redirect, request

from m8flow_backend.errors import ApiError
from m8flow_backend.integrations.auth import get_auth_provider
from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, TokenInvalid
from m8flow_backend.integrations.auth.base.models import IssuerRef
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.routes.session_cookies import (
    clear_session_cookie,
    clear_session_cookies,
    set_session_cookie,
    set_token_cookies,
    token_set_as_dict,
)
from m8flow_backend.routes.safe_redirect import (
    require_safe_redirect_url,
    safe_redirect_or_fallback,
)

logger = logging.getLogger(__name__)

_OAUTH_NONCE_COOKIE = "m8flow_oauth_nonce"
_LOGIN_RETURN_PATH = "/v1.0/login_return"


def _redirect_uri() -> str:
    """Callback URL registered on the m8flow-backend client (its redirectUris
    entry is a wildcard on this backend's own origin, e.g. http://localhost:6840/*)."""
    return f"{request.host_url.rstrip('/')}{_LOGIN_RETURN_PATH}"


def _encode_state(*, authentication_identifier: str, redirect_url: str, nonce: str) -> str:
    """Base64-encode a Python dict repr for the OAuth `state` param.

    The format (base64 -> ast.literal_eval) is decoded back by login_return in
    this controller.
    """
    state_dict = {
        "authentication_identifier": authentication_identifier,
        "redirect_url": redirect_url,
        "nonce": nonce,
    }
    return base64.b64encode(str(state_dict).encode("utf-8")).decode("ascii")


def _decode_state(state: str | None) -> dict[str, str] | None:
    if not state:
        return None
    try:
        raw = base64.b64decode(unquote(state)).decode("utf-8")
        state_dict = ast.literal_eval(raw)
    except Exception:
        return None
    return state_dict if isinstance(state_dict, dict) else None


def login() -> Response:
    """GET /v1.0/login - start the browser-redirect Keycloak login flow.

    Query params:
      redirect_url (required): where to land in the app after a successful login.
        Must be a relative application path (``/…``) or an absolute URL whose
        origin is on the configured frontend/CORS allowlist.
      authentication_identifier (optional): realm to authenticate against;
        defaults to the shared realm.
      tenant + tenant_finalization (optional): when the browser already has a
        shared-realm session, finalize the active tenant locally (cookie +
        group sync) instead of starting another Keycloak round-trip.
    """
    redirect_url = request.args.get("redirect_url")
    if not redirect_url:
        raise ApiError("redirect_url_required", "redirect_url is required", 400)
    redirect_url = require_safe_redirect_url(redirect_url)

    from m8flow_backend.auth import try_finalize_shared_realm_session

    finalized = try_finalize_shared_realm_session(redirect_url)
    if finalized is not None:
        return finalized

    identifier = (
        (request.args.get("authentication_identifier") or "").strip()
        or get_auth_provider().default_issuer().value
    )
    nonce = secrets.token_urlsafe(24)
    state = _encode_state(authentication_identifier=identifier, redirect_url=redirect_url, nonce=nonce)

    # Optional OIDC prompt (e.g. login) — used after logout so a leftover SSO
    # session in another realm cannot silently re-authenticate.
    prompt = (request.args.get("prompt") or "").strip() or None
    auth_url = get_auth_provider().build_login_url(
        redirect_uri=_redirect_uri(),
        state=state,
        issuer=IssuerRef(value=identifier),
        prompt=prompt,
    )

    response = redirect(auth_url)
    # httpOnly + scoped to the callback path: only ever read back by login_return,
    # never needed (or wanted) in frontend JS.
    set_session_cookie(
        response,
        _OAUTH_NONCE_COOKIE,
        nonce,
        max_age=300,
        path=_LOGIN_RETURN_PATH,
        httponly=True,
    )
    return response


def login_return() -> Response:
    """GET /v1.0/login_return - Keycloak's OAuth authorization-code callback."""
    error = request.args.get("error")
    if error:
        raise ApiError("keycloak_login_failed", request.args.get("error_description") or error, 401)

    state = _decode_state(request.args.get("state"))
    if not state:
        raise ApiError("invalid_state", "Missing or malformed state parameter", 400)

    nonce_cookie = request.cookies.get(_OAUTH_NONCE_COOKIE)
    if not nonce_cookie or nonce_cookie != state.get("nonce"):
        raise ApiError("invalid_state", "state did not match the expected login attempt", 400)

    code = request.args.get("code")
    if not code:
        raise ApiError("missing_code", "code is required", 400)

    identifier = state.get("authentication_identifier") or get_auth_provider().default_issuer().value
    redirect_url = safe_redirect_or_fallback(state.get("redirect_url"))

    try:
        token_set = get_auth_provider().exchange_code(
            code=code,
            redirect_uri=_redirect_uri(),
            issuer=IssuerRef(value=identifier),
        )
    except (TokenInvalid, ProviderUnavailable):
        raise ApiError("keycloak_token_exchange_failed", "Could not complete sign-in", 401) from None

    response = redirect(redirect_url)
    clear_session_cookie(response, _OAUTH_NONCE_COOKIE, path=_LOGIN_RETURN_PATH, httponly=True)
    set_token_cookies(response, token_set_as_dict(token_set), identifier=identifier)
    return response


def refresh() -> Response:
    """POST /v1.0/refresh - silently mint fresh tokens from the refresh_token
    cookie, without sending the browser back through Keycloak's /auth
    endpoint. See the module docstring for why this exists.

    Returns 401 (no cookies changed) if there's no refresh_token cookie or
    Keycloak rejects it (expired/revoked); the caller is expected to fall
    back to the full GET /v1.0/login redirect in that case.
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise ApiError("no_refresh_token", "No refresh token cookie present", 401)

    identifier = request.cookies.get("authentication_identifier") or get_auth_provider().default_issuer().value

    try:
        token_set = get_auth_provider().refresh(
            refresh_token=refresh_token,
            issuer=IssuerRef(value=identifier),
        )
    except (TokenInvalid, ProviderUnavailable):
        raise ApiError("keycloak_refresh_failed", "Could not refresh session", 401) from None

    response = jsonify({"ok": True})
    set_token_cookies(response, token_set_as_dict(token_set), identifier=identifier)
    return response


def logout() -> Response:
    """GET /v1.0/logout - clear the app session and end the Keycloak SSO session.

    Query params (matching m8flow-frontend's UserService.doLogout()):
      redirect_url: where to land after logout.
      id_token: the session's id_token, used as Keycloak's id_token_hint.
      authentication_identifier (optional): defaults to the session's cookie,
        then the shared realm.
      backend_only=true (optional): skip the Keycloak round trip entirely
        (used for anonymous/public-user sessions with no real Keycloak login).
    """
    redirect_url = safe_redirect_or_fallback(request.args.get("redirect_url") or "/")
    identifier = (
        request.args.get("authentication_identifier")
        or request.cookies.get("authentication_identifier")
        or get_auth_provider().default_issuer().value
    )
    id_token = request.args.get("id_token") or request.cookies.get("id_token")
    backend_only = (request.args.get("backend_only") or "").strip().lower() == "true"

    if not backend_only and id_token:
        target = get_auth_provider().build_logout_url(
            issuer=IssuerRef(value=identifier),
            redirect_uri=redirect_url,
            id_token_hint=id_token,
        )
    else:
        target = redirect_url

    response = redirect(target)
    clear_session_cookies(response)
    clear_session_cookie(response, "m8flow_auth_realm")
    # A full logout should not let the next sign-in silently inherit the
    # previous session's tenant selection.
    clear_session_cookie(response, SELECTED_TENANT_COOKIE_NAME)
    _clear_active_tenant_best_effort(id_token)
    return response


def _clear_active_tenant_best_effort(id_token: str | None) -> None:
    """Clear the Keycloak ``m8flow_active_tenant`` attribute so a stale
    server-side "active org" can't survive a full logout and let the next
    login's token silently resume the previous session's tenant. Best-effort:
    logout must still succeed even if this fails."""
    if not id_token:
        return
    from m8flow_backend.auth import decode_auth_token

    try:
        payload = decode_auth_token(id_token)
        username = payload.get("preferred_username")
        if username:
            get_auth_provider().clear_active_tenant(username=str(username))
    except Exception:
        logger.warning("logout: unable to clear active-tenant attribute", exc_info=True)
