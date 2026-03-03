from __future__ import annotations

import ast
import base64
import logging
from urllib.parse import unquote
from urllib.parse import urlsplit

from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant
from spiffworkflow_backend.routes import authentication_controller

logger = logging.getLogger(__name__)

_PATCHED = False
_DECODE_TOKEN_PATCHED = False
_MASTER_REALM_PATCHED = False

# Path suffixes that may be called with Keycloak master realm tokens (bootstrap/admin).
M8FLOW_MASTER_REALM_PATH_SUBSTRINGS = ("/m8flow/tenant-realms", "/m8flow/create-tenant")
LOGIN_RETURN_PATH_SUBSTRING = "/login_return"


def apply() -> None:
    """Patch the authentication controller to resolve tenant after auth."""
    global _PATCHED
    if _PATCHED:
        return

    original = authentication_controller.omni_auth

    def patched_omni_auth(*args, **kwargs):
        rv = original(*args, **kwargs)
        # Resolve tenant as soon as auth has populated g.token/cookies (uses canonical db).
        resolve_request_tenant()
        return rv

    authentication_controller.omni_auth = patched_omni_auth  # type: ignore[assignment]
    _PATCHED = True


def _patched_get_decoded_token(token: str):
    return authentication_controller._original_get_decoded_token(token)


def apply_decode_token_debug_patch() -> None:
    global _DECODE_TOKEN_PATCHED
    if _DECODE_TOKEN_PATCHED:
        return
    authentication_controller._original_get_decoded_token = authentication_controller._get_decoded_token
    authentication_controller._get_decoded_token = _patched_get_decoded_token
    _DECODE_TOKEN_PATCHED = True


def _authentication_identifier_from_state() -> str | None:
    """On login_return, state contains base64 dict with authentication_identifier."""
    from flask import request

    path = (request.path or "").strip()
    if LOGIN_RETURN_PATH_SUBSTRING not in path:
        return None
    state = request.args.get("state")
    if not state or not isinstance(state, str):
        return None
    try:
        state = unquote(state)
        raw = base64.b64decode(state).decode("utf-8")
        state_dict = ast.literal_eval(raw)
        return state_dict.get("authentication_identifier")
    except Exception:
        return None


def _has_master_auth_config() -> bool:
    """True if SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS has identifier='master'."""
    from flask import current_app

    configs = current_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    return any(isinstance(c, dict) and c.get("identifier") == "master" for c in configs)


def _auth_config_identifiers() -> list[str]:
    """Return auth config identifiers (e.g., realm names)."""
    from flask import current_app

    configs = current_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    return [c["identifier"] for c in configs if isinstance(c, dict) and c.get("identifier")]


def _authentication_identifier_from_bearer_token() -> str | None:
    """
    Decode Bearer payload without signature verification and derive identifier from:
    - m8flow_tenant_name / realm_name
    - fallback: last segment of iss (.../realms/<realm>)
    """
    from flask import request

    auth_header = (request.headers.get("Authorization") or "").strip()
    if not auth_header.startswith("Bearer ") or len(auth_header) <= 7:
        return None
    token = auth_header[7:].strip()
    if not token:
        return None

    try:
        import jwt

        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    realm_name = payload.get("m8flow_tenant_name") or payload.get("realm_name")
    if isinstance(realm_name, str) and realm_name.strip():
        identifiers = _auth_config_identifiers()
        if realm_name in identifiers:
            return realm_name

    iss = payload.get("iss")
    if isinstance(iss, str) and iss.strip():
        realm_from_iss = iss.rstrip("/").split("/")[-1]
        if realm_from_iss:
            identifiers = _auth_config_identifiers()
            if realm_from_iss in identifiers:
                return realm_from_iss

    return None


def apply_master_realm_auth_patch() -> None:
    """Patch identifier resolution for master/bootstrap and Bearer-only requests."""
    global _MASTER_REALM_PATCHED
    if _MASTER_REALM_PATCHED:
        return
    from flask import request

    original = authentication_controller._get_authentication_identifier_from_request

    def _patched_get_authentication_identifier_from_request() -> str:
        path = (request.path or "").strip()
        state_id = _authentication_identifier_from_state()
        if state_id:
            return state_id

        auth_header = (request.headers.get("Authorization") or "").strip()
        has_bearer = auth_header.startswith("Bearer ") and len(auth_header) > 7
        cookie_id = request.cookies.get("authentication_identifier")
        header_id = request.headers.get("SpiffWorkflow-Authentication-Identifier")
        path_match = any(s in path for s in M8FLOW_MASTER_REALM_PATH_SUBSTRINGS)
        has_master_config = _has_master_auth_config()

        if has_bearer and not cookie_id and not header_id and path_match and has_master_config:
            return "master"

        if has_bearer and not cookie_id and not header_id:
            derived = _authentication_identifier_from_bearer_token()
            if derived:
                return derived

        return original()

    authentication_controller._get_authentication_identifier_from_request = (
        _patched_get_authentication_identifier_from_request
    )
    _MASTER_REALM_PATCHED = True
    logger.info(
        "master_realm_auth_patch: create-realm/create-tenant may use 'master' when Bearer present, no identifier, and master config exists."
    )


def _handle_tenant_login_request(flask_app):
    """If request is GET .../login with tenant param, handle redirect and return response or None."""
    from flask import jsonify, redirect, request
    from m8flow_backend.services.auth_config_service import ensure_tenant_auth_config
    from m8flow_backend.services.keycloak_service import realm_exists
    from spiffworkflow_backend.services.authentication_service import AuthenticationService

    api_prefix = flask_app.config.get("SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX", "/v1.0")
    if not request.path.startswith(api_prefix) or not request.path.rstrip("/").endswith("/login"):
        return None
    if request.method != "GET":
        return None

    tenant = request.args.get("tenant")
    if not tenant or not str(tenant).strip():
        return None
    tenant = str(tenant).strip()

    redirect_url = request.args.get("redirect_url") or flask_app.config.get(
        "SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", "/"
    )
    frontend_url = str(flask_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", ""))
    if not _is_allowed_frontend_redirect_url(redirect_url, frontend_url):
        return jsonify({"detail": "Invalid redirect_url"}), 400

    if not realm_exists(tenant):
        return jsonify({"detail": "Tenant realm not found"}), 404

    ensure_tenant_auth_config(flask_app, tenant)
    login_redirect_url = AuthenticationService().get_login_redirect_url(
        authentication_identifier=tenant, final_url=redirect_url
    )
    return redirect(login_redirect_url)


def _origin_tuple(url: str) -> tuple[str, str, int | None] | None:
    """Return normalized (scheme, host, port) for absolute URLs."""
    try:
        parsed = urlsplit((url or "").strip())
    except ValueError:
        return None

    if not parsed.scheme or not parsed.hostname:
        return None

    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return None

    if port is None:
        if scheme == "http":
            port = 80
        elif scheme == "https":
            port = 443

    return (scheme, host, port)


def _is_allowed_frontend_redirect_url(redirect_url: str, frontend_url: str) -> bool:
    """
    Allow:
    - Relative paths (`/tasks`, `/tasks?foo=bar`) for same-origin frontend redirects.
    - Absolute URLs whose origin exactly matches SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND.
    Reject:
    - Prefix tricks like `https://app.example.com.evil.com`.
    - Scheme-relative URLs (`//evil.com`).
    """
    redirect = (redirect_url or "").strip()
    frontend = (frontend_url or "").strip()

    if not frontend:
        return True

    frontend_origin = _origin_tuple(frontend)
    if frontend_origin is None:
        return False

    if redirect.startswith("/") and not redirect.startswith("//"):
        return True

    redirect_origin = _origin_tuple(redirect)
    if redirect_origin is None:
        return False

    return redirect_origin == frontend_origin


def apply_login_tenant_patch(flask_app) -> None:
    """Register a before_request handler to intercept login when tenant param is present."""
    if getattr(flask_app, "_m8flow_login_tenant_patch_applied", False):
        return

    from m8flow_backend.services.auth_config_service import ensure_realm_identifier_in_auth_configs

    ensure_realm_identifier_in_auth_configs(flask_app)

    def before_login_tenant():
        resp = _handle_tenant_login_request(flask_app)
        if resp is not None:
            return resp

    before_login_tenant._m8flow_login_tenant_patch = True  # type: ignore[attr-defined]
    before_request_funcs = flask_app.before_request_funcs.setdefault(None, [])
    if any(getattr(func, "_m8flow_login_tenant_patch", False) for func in before_request_funcs):
        flask_app._m8flow_login_tenant_patch_applied = True
        return

    flask_app.before_request(before_login_tenant)
    flask_app._m8flow_login_tenant_patch_applied = True
    logger.info("login_tenant_patch: applied tenant-aware login redirect")
