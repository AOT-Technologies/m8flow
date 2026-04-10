from __future__ import annotations

import ast
import base64
from contextlib import contextmanager
from functools import wraps
from ipaddress import ip_address
import logging
import re
from urllib.parse import unquote
from urllib.parse import urlsplit

from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant
from m8flow_backend.services.tenant_identity_helpers import temporary_qualified_group_config
from m8flow_backend.tenancy import TENANT_CLAIM
from spiffworkflow_backend.routes import authentication_controller

logger = logging.getLogger(__name__)

_PATCHED = False
_COOKIE_DOMAIN_PATCHED = False
_DECODE_TOKEN_PATCHED = False
_MASTER_REALM_PATCHED = False
_PUBLIC_GROUP_PATCHED = False
_REFRESH_TOKEN_TENANT_PATCHED = False

# Path suffixes that may be called with Keycloak master realm tokens (bootstrap/global admin).
M8FLOW_MASTER_REALM_PATH_SUBSTRINGS = (
    "/m8flow/tenant-realms",
    "/m8flow/create-tenant",
    "/m8flow/tenants",
)
LOGIN_RETURN_PATH_SUBSTRING = "/login_return"
_MISSING = object()


def apply() -> None:
    """Patch the authentication controller with m8flow auth behavior."""
    apply_cookie_domain_patch()
    apply_public_group_patch()

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


def apply_public_group_patch() -> None:
    global _PUBLIC_GROUP_PATCHED
    if _PUBLIC_GROUP_PATCHED:
        return

    original = authentication_controller._check_if_request_is_public

    @wraps(original)
    def patched_check_if_request_is_public():
        with temporary_qualified_group_config("SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"):
            return original()

    authentication_controller._check_if_request_is_public = patched_check_if_request_is_public
    _PUBLIC_GROUP_PATCHED = True


def _frontend_cookie_domain(frontend_url: str) -> str | None:
    """
    Return a valid cookie domain for the configured frontend URL.

    Browsers reject cookie Domain values that include a port, and they are also
    picky about localhost/IP literals. For local development on localhost or a
    LAN IP, host-only cookies are the most reliable choice, so return None.
    """
    candidate = (frontend_url or "").strip()
    if not candidate:
        return None

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
    except ValueError:
        hostname = None

    if not hostname:
        hostname = re.sub(r"^https?:\/\/", "", candidate).split("/")[0].split(":")[0].strip() or None

    if not hostname:
        return None

    if hostname == "localhost" or "." not in hostname:
        return None

    try:
        ip_address(hostname)
        return None
    except ValueError:
        return hostname


@contextmanager
def _temporary_frontend_url(frontend_url: str):
    from flask import current_app

    previous = current_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND")
    current_app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = frontend_url
    try:
        yield
    finally:
        current_app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = previous


def apply_cookie_domain_patch() -> None:
    global _COOKIE_DOMAIN_PATCHED
    if _COOKIE_DOMAIN_PATCHED:
        return

    original = authentication_controller._set_new_access_token_in_cookie

    @wraps(original)
    def patched_set_new_access_token_in_cookie(response):
        from flask import current_app

        frontend_url = str(current_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", ""))
        cookie_domain = _frontend_cookie_domain(frontend_url)
        patched_frontend_url = "localhost" if cookie_domain is None else f"https://{cookie_domain}"

        cookies_before = len(response.headers.getlist("Set-Cookie"))

        with _temporary_frontend_url(patched_frontend_url):
            result = original(response)

        cookies_after = len(result.headers.getlist("Set-Cookie"))
        if cookies_after != cookies_before:
            result.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            result.headers["Pragma"] = "no-cache"

        return result

    authentication_controller._set_new_access_token_in_cookie = patched_set_new_access_token_in_cookie
    _COOKIE_DOMAIN_PATCHED = True


def _decode_state_authentication_identifier(state: str | None) -> str | None:
    if not state:
        return None
    try:
        raw = base64.b64decode(unquote(state)).decode("utf-8")
        state_dict = ast.literal_eval(raw)
    except Exception:
        return None
    identifier = state_dict.get("authentication_identifier") if isinstance(state_dict, dict) else None
    if isinstance(identifier, str) and identifier.strip():
        return identifier
    return None


def _tenant_for_refresh_tokens(
    decoded_token: dict | None = None,
    state: str | None = None,
) -> str | None:
    from flask import g, has_request_context, request

    if isinstance(decoded_token, dict):
        tenant_from_claim = decoded_token.get(TENANT_CLAIM)
        if isinstance(tenant_from_claim, str) and tenant_from_claim.strip():
            return tenant_from_claim

    state_identifier = _decode_state_authentication_identifier(state)
    if state_identifier:
        return state_identifier

    if not has_request_context():
        return None

    existing_tenant = getattr(g, "m8flow_tenant_id", None)
    if isinstance(existing_tenant, str) and existing_tenant.strip():
        return existing_tenant

    request_state_identifier = _decode_state_authentication_identifier(request.args.get("state"))
    if request_state_identifier:
        return request_state_identifier

    cookie_identifier = request.cookies.get("authentication_identifier")
    if cookie_identifier:
        return cookie_identifier

    header_identifier = request.headers.get("SpiffWorkflow-Authentication-Identifier")
    if header_identifier:
        return header_identifier

    return None


@contextmanager
def _temporary_request_tenant(tenant_id: str | None):
    from flask import g, has_request_context

    if not has_request_context() or not tenant_id:
        yield
        return

    previous = getattr(g, "m8flow_tenant_id", _MISSING)
    if previous is _MISSING or previous is None:
        g.m8flow_tenant_id = tenant_id
    try:
        yield
    finally:
        if previous is _MISSING:
            if hasattr(g, "m8flow_tenant_id"):
                delattr(g, "m8flow_tenant_id")
        else:
            g.m8flow_tenant_id = previous


def apply_refresh_token_tenant_patch() -> None:
    """
    Ensure refresh-token operations have tenant context during auth controller
    flows that run before tenant-resolution hooks.
    """
    global _REFRESH_TOKEN_TENANT_PATCHED
    if _REFRESH_TOKEN_TENANT_PATCHED:
        return

    original_login_return = authentication_controller.login_return
    original_get_user_model_from_token = authentication_controller._get_user_model_from_token

    @wraps(original_login_return)
    def patched_login_return(*args, **kwargs):
        from flask import current_app, redirect
        from spiffworkflow_backend.services.authentication_service import AuthenticationService

        state = kwargs.get("state")
        if state is None and args:
            state = args[0]

        error = kwargs.get("error")
        error_description = kwargs.get("error_description")
        if error and error_description and "authentication_expired" in str(error_description):
            try:
                decoded_state = unquote(state) if isinstance(state, str) else ""
                state_dict = ast.literal_eval(base64.b64decode(decoded_state).decode("utf-8"))

                auth_id = state_dict.get("authentication_identifier")
                final_url = state_dict.get("final_url") or "/"
                frontend_url = str(current_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", ""))

                if not _is_allowed_frontend_redirect_url(final_url, frontend_url):
                    final_url = frontend_url or "/"

                if auth_id:
                    login_url = AuthenticationService().get_login_redirect_url(
                        authentication_identifier=auth_id,
                        final_url=final_url,
                    )
                    if "prompt=" not in login_url:
                        login_url += "&prompt=login"
                    logger.info("authentication_expired detected, retrying login for identifier=%s", auth_id)
                    return redirect(login_url)
            except Exception:
                logger.warning("Failed to auto-retry login after authentication_expired", exc_info=True)

        tenant_id = _tenant_for_refresh_tokens(state=state if isinstance(state, str) else None)
        auth_identifier = _authentication_identifier_from_state() or (
            _decode_state_authentication_identifier(state) if isinstance(state, str) else None
        )
        if auth_identifier:
            try:
                from m8flow_backend.services.keycloak_service import (
                    ensure_backend_redirect_uri_in_keycloak_client,
                )

                ensure_backend_redirect_uri_in_keycloak_client(auth_identifier)
            except Exception:
                pass
        with _temporary_request_tenant(tenant_id):
            return original_login_return(*args, **kwargs)

    @wraps(original_get_user_model_from_token)
    def patched_get_user_model_from_token(decoded_token: dict):
        tenant_id = _tenant_for_refresh_tokens(decoded_token=decoded_token)
        with _temporary_request_tenant(tenant_id):
            try:
                return original_get_user_model_from_token(decoded_token)
            except Exception as exc:
                from spiffworkflow_backend.exceptions.api_error import ApiError

                if not isinstance(exc, ApiError) or exc.error_code != "invalid_user":
                    raise
                if not isinstance(decoded_token, dict) or "iss" not in decoded_token or "sub" not in decoded_token:
                    raise

                from spiffworkflow_backend.services.authorization_service import AuthorizationService

                user_model = AuthorizationService.create_user_from_sign_in(decoded_token)
                logger.info(
                    "refresh_token_tenant_patch: auto-provisioned missing user for issuer=%s subject=%s",
                    decoded_token.get("iss"),
                    decoded_token.get("sub"),
                )
                return user_model

    authentication_controller.login_return = patched_login_return  # type: ignore[assignment]
    authentication_controller._get_user_model_from_token = patched_get_user_model_from_token  # type: ignore[assignment]
    _REFRESH_TOKEN_TENANT_PATCHED = True


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
        "master_realm_auth_patch: global tenant-management endpoints may use 'master' when Bearer is present, no identifier is supplied, and a master auth config exists."
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

    from m8flow_backend.services.auth_config_service import (
        ensure_master_auth_config,
        ensure_realm_identifier_in_auth_configs,
    )

    ensure_realm_identifier_in_auth_configs(flask_app)
    ensure_master_auth_config(flask_app)

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
