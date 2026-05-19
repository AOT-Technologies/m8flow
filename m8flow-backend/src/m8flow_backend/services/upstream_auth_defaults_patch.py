from __future__ import annotations

import os

DEFAULT_CLIENT_ID = "m8flow-backend"
DEFAULT_CLIENT_SECRET = "JXeQExm0JhQPLumgHtIIqf52bDalHz0q"
UPSTREAM_REALM_URI = "http://localhost:7002/realms/spiffworkflow-local"

_PATCHED = False


def _setdefault_env(key: str, value: str) -> None:
    if not os.environ.get(key):
        os.environ[key] = value


def _normalize_auth_config_keys(auth_config: dict) -> dict:
    normalized = {}
    for key, value in auth_config.items():
        normalized_key = key.lower() if isinstance(key, str) else key
        if normalized_key not in normalized:
            normalized[normalized_key] = value
    return normalized


def _has_structured_auth_configs() -> bool:
    return any(
        key == "SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS" or key.startswith("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__")
        for key in os.environ
    )


def _public_keycloak_base() -> str:
    return (
        os.environ.get("KEYCLOAK_HOSTNAME")
        or os.environ.get("M8FLOW_KEYCLOAK_PUBLIC_ISSUER_BASE")
        or os.environ.get("KEYCLOAK_URL")
        or os.environ.get("M8FLOW_KEYCLOAK_URL")
        or "http://localhost:7002"
    ).rstrip("/")


def _internal_keycloak_base() -> str:
    return (
        os.environ.get("KEYCLOAK_URL")
        or os.environ.get("M8FLOW_KEYCLOAK_URL")
        or _public_keycloak_base()
    ).rstrip("/")


def _shared_realm_name() -> str:
    from m8flow_backend.config import shared_realm_name

    return shared_realm_name()


def _shared_realm_label() -> str:
    from m8flow_backend.config import shared_realm_label

    return shared_realm_label()


def _master_realm_name() -> str:
    from m8flow_backend.config import master_realm_name

    return master_realm_name()


def apply_runtime(flask_app) -> None:
    """Normalize runtime auth defaults after upstream config has been loaded."""
    if flask_app.config.get("SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID") == "spiffworkflow-backend":
        flask_app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID"] = DEFAULT_CLIENT_ID

    shared_realm_name = _shared_realm_name()
    shared_realm_label = _shared_realm_label()
    shared_realm_uri = f"{_public_keycloak_base()}/realms/{shared_realm_name}"
    master_realm_name = _master_realm_name()
    auth_configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    normalized_auth_configs = []
    for auth_config in auth_configs:
        if not isinstance(auth_config, dict):
            normalized_auth_configs.append(auth_config)
            continue
        auth_config = _normalize_auth_config_keys(auth_config)
        normalized_auth_configs.append(auth_config)
        identifier = str(auth_config.get("identifier") or "").strip()
        uri = str(auth_config.get("uri") or "").strip()
        internal_uri = str(auth_config.get("internal_uri") or "").strip()
        default_alias_points_to_shared_realm = identifier == "default" and any(
            candidate in {UPSTREAM_REALM_URI, shared_realm_uri}
            or candidate.endswith(f"/realms/{shared_realm_name}")
            for candidate in (uri, internal_uri)
            if candidate
        )
        if default_alias_points_to_shared_realm:
            auth_config["identifier"] = shared_realm_name
            identifier = shared_realm_name
            if str(auth_config.get("label") or "").strip().lower() in {"", "default"}:
                auth_config["label"] = shared_realm_label
        if not auth_config.get("label"):
            auth_config["label"] = (
                "Master"
                if identifier == master_realm_name
                else (shared_realm_label if identifier == shared_realm_name else (identifier or "Default"))
            )
        if auth_config.get("client_id") == "spiffworkflow-backend":
            auth_config["client_id"] = DEFAULT_CLIENT_ID
        if auth_config.get("uri") == UPSTREAM_REALM_URI:
            auth_config["uri"] = shared_realm_uri
        if auth_config.get("internal_uri") == UPSTREAM_REALM_URI:
            auth_config["internal_uri"] = shared_realm_uri

    flask_app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = normalized_auth_configs


def apply() -> None:
    """Seed M8Flow auth defaults without importing upstream modules before override bootstrap."""
    global _PATCHED
    if _PATCHED:
        return

    _setdefault_env("SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID", DEFAULT_CLIENT_ID)

    if not _has_structured_auth_configs() and not os.environ.get("SPIFFWORKFLOW_BACKEND_OPEN_ID_SERVER_URL"):
        shared_realm_name = _shared_realm_name()
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__identifier", shared_realm_name)
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__label", _shared_realm_label())
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__uri", f"{_public_keycloak_base()}/realms/{shared_realm_name}")
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__internal_uri", f"{_internal_keycloak_base()}/realms/{shared_realm_name}")
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__client_id", DEFAULT_CLIENT_ID)
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__client_secret", DEFAULT_CLIENT_SECRET)

    _PATCHED = True
