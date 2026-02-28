from __future__ import annotations

import copy
import logging

logger = logging.getLogger(__name__)

# Realm name used by Keycloak and by the frontend cookie authentication_identifier.
SPIFFWORKFLOW_LOCAL_REALM = "spiffworkflow-local"


def ensure_realm_identifier_in_auth_configs(flask_app) -> None:
    """
    Ensure SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS has an entry with identifier matching
    the realm when any config URI points at .../realms/spiffworkflow-local.
    """
    configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    if not configs:
        return
    if any(c.get("identifier") == SPIFFWORKFLOW_LOCAL_REALM for c in configs):
        return

    template = None
    for c in configs:
        uri = (c.get("uri") or "").strip()
        if f"/realms/{SPIFFWORKFLOW_LOCAL_REALM}" in uri or uri.endswith(
            f"/realms/{SPIFFWORKFLOW_LOCAL_REALM}"
        ):
            template = c
            break
    if not template:
        return

    new_config = copy.deepcopy(template)
    new_config["identifier"] = SPIFFWORKFLOW_LOCAL_REALM
    new_config["label"] = new_config.get("label") or SPIFFWORKFLOW_LOCAL_REALM
    configs.append(new_config)
    logger.info(
        "auth_config_service: added auth config identifier=%s so cookie authentication_identifier matches",
        SPIFFWORKFLOW_LOCAL_REALM,
    )


def ensure_tenant_auth_config(flask_app, tenant: str) -> None:
    """Ensure SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS has an entry for this tenant realm."""
    configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    if any(c.get("identifier") == tenant for c in configs):
        return

    # Use the first config as template (usually "default" with Keycloak realm).
    if not configs:
        logger.warning("auth_config_service: no auth configs; cannot add tenant %s", tenant)
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
        logger.info("auth_config_service: added auth config for tenant realm %s", tenant)
    except Exception as exc:
        logger.warning("auth_config_service: failed to add auth config for %s: %s", tenant, exc)
