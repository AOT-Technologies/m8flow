# extensions/master_realm_auth_patch.py
# 1) For create-realm and create-tenant APIs, use Keycloak master realm for token validation
#    when the request has a Bearer token but no authentication_identifier (cookie/header).
# 2) On login_return callback, use authentication_identifier from OAuth state so token
#    decode uses the correct realm's JWKS (cookie is not set yet on that request).

import ast
import base64
import logging
from urllib.parse import unquote

logger = logging.getLogger(__name__)

# Path suffixes that may be called with Keycloak master realm tokens (bootstrap/admin).
M8FLOW_MASTER_REALM_PATH_SUBSTRINGS = ("/m8flow/tenant-realms", "/m8flow/create-tenant")
LOGIN_RETURN_PATH_SUBSTRING = "/login_return"

# #region agent log
def _debug_log(hypothesis_id: str, message: str, data: dict) -> None:
    import json
    import time
    try:
        with open("/Users/aot/Development/AOT/m8Flow/vinaayakh-m8flow/.cursor/debug.log", "a") as f:
            f.write(json.dumps({"hypothesisId": hypothesis_id, "message": message, "data": data, "timestamp": int(time.time() * 1000), "sessionId": "debug-session", "runId": "run1", "location": "master_realm_auth_patch.py"}) + "\n")
    except Exception:
        pass
# #endregion


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
        # #region agent log
        _debug_log("H1", "auth identifier resolution", {"path": path, "has_bearer": has_bearer, "cookie_id": cookie_id is not None, "header_id": header_id, "path_match": path_match, "has_master_config": has_master_config})
        # #endregion

        if (
            has_bearer
            and not cookie_id
            and not header_id
            and path_match
            and has_master_config
        ):
            # #region agent log
            _debug_log("H2", "returning master", {"result": "master"})
            # #endregion
            return "master"
        result = _original()
        # #region agent log
        _debug_log("H1", "returning original", {"result": result})
        # #endregion
        return result

    authentication_controller._get_authentication_identifier_from_request = (
        _patched_get_authentication_identifier_from_request
    )
    logger.info(
        "master_realm_auth_patch: create-realm/create-tenant may use 'master' when Bearer present, no identifier, and master config exists."
    )
