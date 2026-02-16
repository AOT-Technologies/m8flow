# extensions/login_tenant_patch.py
"""Adds a before_request handler for /login and mutates SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS;"""

import copy
import logging
import re

from flask import request

logger = logging.getLogger(__name__)

# Realm name used by Keycloak and by the frontend cookie authentication_identifier.
# If the backend has a config with uri .../realms/spiffworkflow-local but identifier e.g. "default",
# token decode fails because the cookie sends "spiffworkflow-local". We ensure an alias exists.
SPIFFWORKFLOW_LOCAL_REALM = "spiffworkflow-local"


def _ensure_realm_identifier_in_auth_configs(flask_app) -> None:
    """
    Ensure SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS has an entry with identifier matching the realm
    when any config's URI points at .../realms/spiffworkflow-local. Fixes token decode errors
    when the frontend cookie authentication_identifier is spiffworkflow-local but env uses
    identifier=default.
    """
    configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    if not configs:
        return
    if any(c.get("identifier") == SPIFFWORKFLOW_LOCAL_REALM for c in configs):
        return
    template = None
    for c in configs:
        uri = (c.get("uri") or "").strip()
        if f"/realms/{SPIFFWORKFLOW_LOCAL_REALM}" in uri or uri.endswith(f"/realms/{SPIFFWORKFLOW_LOCAL_REALM}"):
            template = c
            break
    if not template:
        return
    new_config = copy.deepcopy(template)
    new_config["identifier"] = SPIFFWORKFLOW_LOCAL_REALM
    new_config["label"] = new_config.get("label") or SPIFFWORKFLOW_LOCAL_REALM
    configs.append(new_config)
    logger.info(
        "login_tenant_patch: Added auth config identifier=%s so cookie authentication_identifier matches",
        SPIFFWORKFLOW_LOCAL_REALM,
    )


def _ensure_tenant_auth_config(flask_app, tenant: str) -> None:
    """Ensure SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS has an entry for this tenant (realm)."""
    configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    if any(c.get("identifier") == tenant for c in configs):
        return
    # Use the first config as template (usually "default" with Keycloak realm)
    if not configs:
        logger.warning("login_tenant_patch: No auth configs; cannot add tenant %s", tenant)
        return
    template = configs[0]
    try:
        from m8flow_backend.config import keycloak_url
        base = keycloak_url().rstrip("/")
        realm_uri = f"{base}/realms/{tenant}"
        new_config = copy.deepcopy(template)
        new_config["identifier"] = tenant
        new_config["label"] = tenant
        new_config["uri"] = realm_uri
        new_config["internal_uri"] = realm_uri
        configs.append(new_config)
        logger.info("login_tenant_patch: Added auth config for tenant realm %s", tenant)
    except Exception as e:
        logger.warning("login_tenant_patch: Failed to add auth config for %s: %s", tenant, e)


def _handle_tenant_login_request(flask_app):
    """If request is GET .../login with tenant param, handle redirect and return response or None."""
    api_prefix = flask_app.config.get("SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX", "/v1.0")
    if not request.path.startswith(api_prefix) or not request.path.rstrip("/").endswith("/login"):
        return None
    if request.method != "GET":
        return None
    tenant = request.args.get("tenant")
    if not tenant or not str(tenant).strip():
        return None
    tenant = str(tenant).strip()
    redirect_url = request.args.get("redirect_url") or flask_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", "/")
    redirect_url_for_check = redirect_url.rstrip("/")
    frontend_url = str(flask_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", "")).rstrip("/")
    frontend_url = re.sub(r":(80|443)$", "", frontend_url)
    if frontend_url and not redirect_url_for_check.startswith(frontend_url):
        from flask import jsonify
        return jsonify({"detail": "Invalid redirect_url"}), 400
    try:
        from m8flow_backend.services.keycloak_service import realm_exists
    except ImportError:
        logger.warning("login_tenant_patch: m8flow_backend not available")
        return None
    if not realm_exists(tenant):
        from flask import jsonify
        return jsonify({"detail": "Tenant realm not found"}), 404
    _ensure_tenant_auth_config(flask_app, tenant)
    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    login_redirect_url = AuthenticationService().get_login_redirect_url(
        authentication_identifier=tenant, final_url=redirect_url
    )
    from flask import redirect
    return redirect(login_redirect_url)


def apply_login_tenant_patch(flask_app) -> None:
    """Register a before_request handler to intercept login when tenant param is present."""
    _ensure_realm_identifier_in_auth_configs(flask_app)
    def before_login_tenant():
        resp = _handle_tenant_login_request(flask_app)
        if resp is not None:
            return resp

    flask_app.before_request(before_login_tenant)
    logger.info("login_tenant_patch: applied tenant-aware login redirect")
