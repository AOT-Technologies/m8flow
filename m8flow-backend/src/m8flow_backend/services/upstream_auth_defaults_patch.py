from __future__ import annotations

import os

DEFAULT_REALM = "m8flow"
DEFAULT_CLIENT_ID = "m8flow-backend"
DEFAULT_CLIENT_SECRET = "JXeQExm0JhQPLumgHtIIqf52bDalHz0q"
UPSTREAM_REALM_URI = "http://localhost:7002/realms/spiffworkflow-local"
M8FLOW_REALM_URI = f"http://localhost:7002/realms/{DEFAULT_REALM}"
M8FLOW_REALM_LABEL = "M8Flow Realm"

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


def apply_runtime(flask_app) -> None:
    """Normalize runtime auth defaults after upstream config has been loaded."""
    if flask_app.config.get("SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID") == "spiffworkflow-backend":
        flask_app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID"] = DEFAULT_CLIENT_ID

    auth_configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    normalized_auth_configs = []
    for auth_config in auth_configs:
        if not isinstance(auth_config, dict):
            normalized_auth_configs.append(auth_config)
            continue
        auth_config = _normalize_auth_config_keys(auth_config)
        normalized_auth_configs.append(auth_config)
        if not auth_config.get("label"):
            identifier = str(auth_config.get("identifier") or "").strip()
            auth_config["label"] = (
                "Master"
                if identifier == "master"
                else (M8FLOW_REALM_LABEL if identifier == DEFAULT_REALM else (identifier or "Default"))
            )
        if auth_config.get("client_id") == "spiffworkflow-backend":
            auth_config["client_id"] = DEFAULT_CLIENT_ID
        if auth_config.get("uri") == UPSTREAM_REALM_URI:
            auth_config["uri"] = M8FLOW_REALM_URI
        if auth_config.get("internal_uri") == UPSTREAM_REALM_URI:
            auth_config["internal_uri"] = M8FLOW_REALM_URI

    flask_app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = normalized_auth_configs


def apply() -> None:
    """Seed M8Flow auth defaults without importing upstream modules before override bootstrap."""
    global _PATCHED
    if _PATCHED:
        return

    _setdefault_env("SPIFFWORKFLOW_BACKEND_OPEN_ID_CLIENT_ID", DEFAULT_CLIENT_ID)

    if not _has_structured_auth_configs() and not os.environ.get("SPIFFWORKFLOW_BACKEND_OPEN_ID_SERVER_URL"):
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__identifier", "default")
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__label", M8FLOW_REALM_LABEL)
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__uri", f"{_public_keycloak_base()}/realms/{DEFAULT_REALM}")
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__internal_uri", f"{_internal_keycloak_base()}/realms/{DEFAULT_REALM}")
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__client_id", DEFAULT_CLIENT_ID)
        _setdefault_env("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__client_secret", DEFAULT_CLIENT_SECRET)

    _PATCHED = True
