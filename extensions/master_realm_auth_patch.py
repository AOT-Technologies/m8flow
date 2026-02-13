# extensions/master_realm_auth_patch.py
# 1) For create-realm and create-tenant APIs, use Keycloak master realm for token validation
#    when the request has a Bearer token but no authentication_identifier (cookie/header).
# 2) On login_return callback, use authentication_identifier from OAuth state so token
#    decode uses the correct realm's JWKS (cookie is not set yet on that request).
# 3) When Bearer token is present but cookie/header are not, derive authentication_identifier
#    from token claims (realm_name or iss) so the frontend does not need to send the header.

import ast
import base64
import logging
from urllib.parse import unquote

logger = logging.getLogger(__name__)

# Path suffixes that may be called with Keycloak master realm tokens (bootstrap/admin).
M8FLOW_MASTER_REALM_PATH_SUBSTRINGS = ("/m8flow/tenant-realms", "/m8flow/create-tenant")
LOGIN_RETURN_PATH_SUBSTRING = "/login_return"


def _authentication_identifier_from_state() -> str | None:
    """On login_return, state query param contains base64-encoded dict with authentication_identifier. Return it or None."""
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
    """True if SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS has an entry with identifier 'master'."""
    from flask import current_app

    configs = current_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    return any(isinstance(c, dict) and c.get("identifier") == "master" for c in configs)


def _auth_config_identifiers() -> list[str]:
    """Return list of auth config identifiers (e.g. realm names)."""
    from flask import current_app

    configs = current_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    return [c["identifier"] for c in configs if isinstance(c, dict) and c.get("identifier")]


def _authentication_identifier_from_bearer_token() -> str | None:
    """
    If the request has a Bearer token, decode the payload (without verification) and derive
    the authentication identifier from m8flow_tenant_name (Keycloak RealmInfoMapper) or from iss
    (e.g. http://host/realms/<realm_name>). Return the identifier if it matches an auth
    config; otherwise None.
    """
    from flask import request

    auth_header = (request.headers.get("Authorization") or "").strip()
    if not auth_header.startswith("Bearer ") or len(auth_header) <= 7:
        return None
    token = auth_header[7:].strip()
    if not token:
        return None

    try:
        # Decode payload only (no signature verification) to read m8flow_tenant_name or iss
        import jwt
        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    # Prefer m8flow_tenant_name from Keycloak RealmInfoMapper (then legacy realm_name)
    realm_name = payload.get("m8flow_tenant_name") or payload.get("realm_name")
    if isinstance(realm_name, str) and realm_name.strip():
        identifiers = _auth_config_identifiers()
        if realm_name in identifiers:
            return realm_name

    # Fallback: last path segment of iss (Keycloak: http://host/realms/<realm_name>)
    iss = payload.get("iss")
    if isinstance(iss, str) and iss.strip():
        realm_from_iss = iss.rstrip("/").split("/")[-1]
        if realm_from_iss:
            identifiers = _auth_config_identifiers()
            if realm_from_iss in identifiers:
                return realm_from_iss

    return None


def apply_master_realm_auth_patch() -> None:
    """Patch _get_authentication_identifier_from_request so create-realm/create-tenant
    use 'master' when Bearer token is present, no authentication_identifier is set,
    and an auth config for 'master' exists.
    """
    from flask import request

    from spiffworkflow_backend.routes import authentication_controller

    _original = authentication_controller._get_authentication_identifier_from_request

    def _patched_get_authentication_identifier_from_request() -> str:
        path = (request.path or "").strip()
        # login_return callback: cookie not set yet; use state so decode uses correct realm JWKS
        state_id = _authentication_identifier_from_state()
        if state_id:
            return state_id
        auth_header = (request.headers.get("Authorization") or "").strip()
        has_bearer = auth_header.startswith("Bearer ") and len(auth_header) > 7
        cookie_id = request.cookies.get("authentication_identifier")
        header_id = request.headers.get("SpiffWorkflow-Authentication-Identifier")
        path_match = any(s in path for s in M8FLOW_MASTER_REALM_PATH_SUBSTRINGS)
        has_master_config = _has_master_auth_config()

        if (
            has_bearer
            and not cookie_id
            and not header_id
            and path_match
            and has_master_config
        ):
            return "master"
        # Derive from token when cookie/header absent (e.g. API calls with only Bearer)
        if has_bearer and not cookie_id and not header_id:
            derived = _authentication_identifier_from_bearer_token()
            if derived:
                return derived
        result = _original()
        return result

    authentication_controller._get_authentication_identifier_from_request = (
        _patched_get_authentication_identifier_from_request
    )
    logger.info(
        "master_realm_auth_patch: create-realm/create-tenant may use 'master' when Bearer present, no identifier, and master config exists."
    )
