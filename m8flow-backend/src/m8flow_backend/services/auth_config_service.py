from __future__ import annotations

import copy
import logging

logger = logging.getLogger(__name__)


def _append_csv_value(existing: str | None, value: str) -> str:
    items = [item.strip() for item in (existing or "").split(",") if item.strip()]
    if value not in items:
        items.append(value)
    return ",".join(items)


def _shared_realm_name() -> str:
    from m8flow_backend.config import shared_realm_name

    return shared_realm_name()


def _master_realm_name() -> str:
    from m8flow_backend.config import master_realm_name

    return master_realm_name()


def ensure_realm_identifier_in_auth_configs(flask_app) -> None:
    """
    Ensure SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS has an entry with identifier matching
    the shared realm when any config URI points at that realm.
    """
    configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    if not configs:
        return
    shared_realm = _shared_realm_name()
    if any(c.get("identifier") == shared_realm for c in configs):
        return

    template = None
    for c in configs:
        uri = (c.get("uri") or "").strip()
        if f"/realms/{shared_realm}" in uri or uri.endswith(f"/realms/{shared_realm}"):
            template = c
            break
    if not template:
        return

    new_config = copy.deepcopy(template)
    new_config["identifier"] = shared_realm
    new_config["label"] = new_config.get("label") or shared_realm
    configs.append(new_config)
    logger.info(
        "auth_config_service: added auth config identifier=%s so cookie authentication_identifier matches",
        shared_realm,
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
        from m8flow_backend.config import (
            keycloak_public_issuer_base,
            keycloak_url,
            spoke_client_id,
            spoke_client_secret,
        )

        base = keycloak_url().rstrip("/")
        realm_uri = f"{base}/realms/{tenant}"
        new_config = copy.deepcopy(template)
        new_config["identifier"] = tenant
        new_config["label"] = tenant
        new_config["uri"] = realm_uri
        new_config["internal_uri"] = realm_uri

        # Additional valid issuers: include the public issuer when different from internal realm URI.
        public_issuer_base = keycloak_public_issuer_base().rstrip("/")
        public_realm_issuer = f"{public_issuer_base}/realms/{tenant}"
        if public_realm_issuer and public_realm_issuer != realm_uri:
            existing_additional = list(new_config.get("additional_valid_issuers") or [])
            if public_realm_issuer not in existing_additional:
                new_config["additional_valid_issuers"] = [*existing_additional, public_realm_issuer]

        # Use the spoke client for tenant realms created via POST /tenant-realms so redirect URIs match.
        new_config["client_id"] = spoke_client_id()
        spoke_secret = spoke_client_secret()
        if spoke_secret:
            new_config["client_secret"] = spoke_secret

        configs.append(new_config)
        logger.info("auth_config_service: added auth config for tenant realm %s", tenant)

        try:
            from m8flow_backend.services.keycloak_service import ensure_backend_redirect_uri_in_keycloak_client

            ensure_backend_redirect_uri_in_keycloak_client(tenant)
        except Exception as exc:
            logger.debug(
                "auth_config_service: ensure_backend_redirect_uri_in_keycloak_client for %s: %s",
                tenant,
                exc,
            )
    except Exception as exc:
        logger.warning("auth_config_service: failed to add auth config for %s: %s", tenant, exc)


def ensure_master_auth_config(flask_app) -> None:
    """Ensure SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS has an entry for the configured admin realm."""
    configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    master_realm = _master_realm_name()
    if any(c.get("identifier") == master_realm for c in configs):
        return

    try:
        from m8flow_backend.config import keycloak_url, master_client_secret, spoke_client_id

        realm_uri = f"{keycloak_url().rstrip('/')}/realms/{master_realm}"
        template = copy.deepcopy(configs[0]) if configs else {}
        new_config = template if isinstance(template, dict) else {}
        new_config["identifier"] = master_realm
        new_config["label"] = "Master"
        new_config["uri"] = realm_uri
        new_config["internal_uri"] = realm_uri
        new_config["client_id"] = new_config.get("client_id") or spoke_client_id()
        new_config["client_secret"] = new_config.get("client_secret") or master_client_secret()
        new_config["additional_valid_client_ids"] = _append_csv_value(
            new_config.get("additional_valid_client_ids"),
            "admin-cli",
        )
        if new_config.get("additional_valid_issuers") is None:
            new_config["additional_valid_issuers"] = []
        configs.append(new_config)
        logger.info("auth_config_service: added auth config for admin realm %s", master_realm)
    except Exception as exc:
        logger.warning("auth_config_service: failed to add auth config for admin realm %s: %s", master_realm, exc)
