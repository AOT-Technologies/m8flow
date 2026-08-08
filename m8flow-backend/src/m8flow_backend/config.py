"""M8Flow Keycloak configuration from environment."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_KEYCLOAK_CLIENT_SECRET = "JXeQExm0JhQPLumgHtIIqf52bDalHz0q"
DEFAULT_SHARED_REALM_NAME = "m8flow"
DEFAULT_MASTER_REALM_NAME = "master"


def _get(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key)
    if value is not None and value != "":
        return value.strip()
    return default


def _read_env_value_from_file(path_value: str | None) -> str | None:
    if not path_value:
        return None

    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path_value

    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    return value or None


def _get_secret_env_value(*keys: str) -> str | None:
    for key in keys:
        value = _get(key)
        if value is not None:
            return value
    return None


def _env_truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def keycloak_url() -> str:
    """Keycloak base URL (no trailing slash)."""
    url = _get("KEYCLOAK_URL") or _get("M8FLOW_KEYCLOAK_URL") or "http://localhost:6842"
    return url.rstrip("/")


def keycloak_public_issuer_base() -> str:
    """Base URL Keycloak uses for the iss claim in tokens (same as KC_HOSTNAME).
    When this differs from keycloak_url() (e.g. Docker proxy), set KEYCLOAK_HOSTNAME or
    M8FLOW_KEYCLOAK_PUBLIC_ISSUER_BASE so the backend accepts the token issuer."""
    url = _get("KEYCLOAK_HOSTNAME") or _get("M8FLOW_KEYCLOAK_PUBLIC_ISSUER_BASE") or keycloak_url()
    return url.rstrip("/")


def keycloak_admin_user() -> str:
    """Master realm admin username (default is created by Keycloak entrypoint)."""
    return _get("KEYCLOAK_ADMIN_USER") or _get("M8FLOW_KEYCLOAK_ADMIN_USER")


def keycloak_admin_password() -> str:
    """Master realm admin password (from env only)."""
    return _get("KEYCLOAK_ADMIN_PASSWORD") or _get("M8FLOW_KEYCLOAK_ADMIN_PASSWORD") or ""


def shared_realm_name() -> str:
    """Shared tenant-user realm name."""
    return _get("M8FLOW_KEYCLOAK_SHARED_REALM") or DEFAULT_SHARED_REALM_NAME


def shared_realm_label() -> str:
    """Display label for the shared realm auth option."""
    realm_name = shared_realm_name()
    if realm_name == DEFAULT_SHARED_REALM_NAME:
        return "M8Flow Realm"
    return realm_name


def default_organization_alias() -> str:
    """Alias for the default shared-realm organization."""
    return _get("M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS") or shared_realm_name()


def default_organization_name() -> str:
    """Display name for the default shared-realm organization."""
    return _get("M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_NAME") or default_organization_alias()


def master_realm_name() -> str:
    """Platform/bootstrap admin realm name."""
    return _get("M8FLOW_KEYCLOAK_MASTER_REALM") or DEFAULT_MASTER_REALM_NAME


def realm_template_path() -> str:
    """Path to realm template JSON (absolute, or relative to cwd, or default next to package)."""
    raw = _get("M8FLOW_KEYCLOAK_REALM_TEMPLATE_PATH")
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = Path.cwd() / raw
        return str(p)
    # Default: under m8flow-backend extension root (works regardless of cwd)
    _pkg = Path(__file__).resolve().parent  # .../m8flow_backend
    _root = _pkg.parent.parent  # .../m8flow-backend (keycloak/ lives here)
    default = _root / "keycloak" / "realm_exports" / "m8flow-tenant-template.json"
    return str(default)


def keycloak_default_groups_path() -> str:
    """Path to the repo-owned default Keycloak organizational groups config."""
    raw = _get("M8FLOW_KEYCLOAK_DEFAULT_GROUPS_PATH")
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = Path.cwd() / raw
        return str(p)

    package_root = Path(__file__).resolve().parent
    default = package_root / "config" / "keycloak" / "default_groups.json"
    return str(default)


def spoke_keystore_p12_path() -> str | None:
    """Path to PKCS#12 keystore for spoke realm client auth."""
    default = "m8flow-backend/keystore.p12"
    raw = _get("M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12") or default
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / raw
    return str(p) if p.exists() else None


def spoke_keystore_password() -> str:
    """Password for spoke keystore (from env only)."""
    return _get("M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD") or ""


def spoke_client_id() -> str:
    """Client id used in each spoke realm for token/login."""
    return _get("M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID") or "m8flow-backend"


def spoke_client_secret() -> str:
    """Client secret for spoke realm client (from env only). Set M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET when using client-secret auth."""
    return _get("M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET") or ""


def master_client_secret() -> str:
    """Client secret for master realm browser login."""
    return (
        _get("M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET")
        or spoke_client_secret()
        or DEFAULT_KEYCLOAK_CLIENT_SECRET
    )


def template_realm_name() -> str:
    """Realm name in the template (for substitution)."""
    return DEFAULT_SHARED_REALM_NAME

def app_public_base_url() -> str | None:
    """Base URL of the app (frontend at /, backend at /api). Used for tenant realm redirect URI substitution.
    When Keycloak and app are on different hosts, set M8FLOW_APP_PUBLIC_BASE_URL; otherwise KEYCLOAK_HOSTNAME is used."""
    raw = (
        _get("M8FLOW_APP_PUBLIC_BASE_URL")
        or _get("KEYCLOAK_HOSTNAME")
        or _get("KC_HOSTNAME")
        or _get("M8FLOW_KEYCLOAK_PUBLIC_ISSUER_BASE")
    )
    if not raw:
        return None
    return raw.strip().rstrip("/") or None


def redirect_uri_backend_host_and_path() -> str | None:
    """Host and path for backend redirect URIs (e.g. app.example.com/api). Derived from app_public_base_url()."""
    base = app_public_base_url()
    if not base:
        return None
    if "://" not in base:
        base = "https://" + base
    parsed = urlparse(base)
    if not parsed.netloc:
        return None
    return parsed.netloc.rstrip("/") + "/api"


def redirect_uri_frontend_host() -> str | None:
    """Host for frontend redirect URIs (e.g. app.example.com). Derived from app_public_base_url()."""
    base = app_public_base_url()
    if not base:
        return None
    if "://" not in base:
        base = "https://" + base
    parsed = urlparse(base)
    if not parsed.netloc:
        return None
    return parsed.netloc


def vault_addr() -> str | None:
    """Vault base URL for API requests."""
    return _get("M8FLOW_VAULT_ADDR") or _get("VAULT_ADDR")


def vault_token() -> str | None:
    """Vault token used for secret operations."""
    return _get_secret_env_value(
        "M8FLOW_VAULT_TOKEN",
        "VAULT_TOKEN",
    ) or _read_env_value_from_file(
        _get_secret_env_value("M8FLOW_VAULT_TOKEN_FILE", "VAULT_TOKEN_FILE")
    )


def vault_role_id() -> str | None:
    """Vault AppRole role ID used for secret operations."""
    return _get_secret_env_value(
        "M8FLOW_VAULT_ROLE_ID",
        "VAULT_ROLE_ID",
    ) or _read_env_value_from_file(
        _get_secret_env_value("M8FLOW_VAULT_ROLE_ID_FILE", "VAULT_ROLE_ID_FILE")
    )


def vault_secret_id() -> str | None:
    """Vault AppRole secret ID used for secret operations."""
    return _get_secret_env_value(
        "M8FLOW_VAULT_SECRET_ID",
        "VAULT_SECRET_ID",
    ) or _read_env_value_from_file(
        _get_secret_env_value("M8FLOW_VAULT_SECRET_ID_FILE", "VAULT_SECRET_ID_FILE")
    )


def vault_namespace() -> str | None:
    """Vault Enterprise namespace, when required."""
    return _get("M8FLOW_VAULT_NAMESPACE") or _get("VAULT_NAMESPACE")


def vault_mount_point() -> str:
    """KV mount point used for M8Flow-managed secrets."""
    return _get("M8FLOW_VAULT_MOUNT_POINT") or "kv"


def vault_secret_path_prefix() -> str:
    """Path prefix inside the KV mount where M8Flow stores secrets."""
    return _get("M8FLOW_VAULT_SECRET_PATH_PREFIX") or "m8flow"


def vault_timeout_seconds() -> float:
    """Timeout used for Vault API calls."""
    raw = _get("M8FLOW_VAULT_TIMEOUT_SECONDS") or "5"
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 5.0


def vault_verify() -> bool | str:
    """TLS verification setting for Vault requests.

    Returns a CA bundle path when configured, ``False`` when verification is
    explicitly disabled, otherwise ``True``.
    """
    ca_cert_path = _get("M8FLOW_VAULT_CACERT") or _get("VAULT_CACERT")
    if ca_cert_path:
        path = Path(ca_cert_path)
        if not path.is_absolute():
            path = Path.cwd() / ca_cert_path
        return str(path)

    if _env_truthy(_get("M8FLOW_VAULT_SKIP_VERIFY") or _get("VAULT_SKIP_VERIFY")):
        return False

    return True


def vault_config_requested() -> bool:
    """Whether any explicit Vault connection settings were supplied."""
    return any((vault_addr(), vault_token(), vault_role_id(), vault_secret_id(), vault_namespace()))


def vault_enabled() -> bool:
    """Whether Vault-backed secret storage is enabled."""
    return _env_truthy(_get("M8FLOW_VAULT_ENABLED"))


def nats_token_salt() -> str:
    """Get the NATS token salt from environment variables."""
    return _get("M8FLOW_NATS_TOKEN_SALT") or "m8flow_default_salt"


def nats_url() -> str:
    """Get the NATS URL from environment variables."""
    return _get("M8FLOW_NATS_URL")


def nats_enabled() -> bool:
    """Whether the NATS event-driven integration is switched on."""
    return (_get("M8FLOW_NATS_ENABLED") or "false").lower() == "true"


def nats_events_stream_name() -> str:
    """JetStream stream for external trigger events published by the
    m8flow-trigger webhook."""
    return _get("M8FLOW_NATS_EVENTS_STREAM_NAME") or "M8FLOW_EVENTS"


def nats_notifications_stream_name() -> str:
    """JetStream stream for notification events — separate from the
    trigger stream so the engine consumer never receives notification traffic."""
    return _get("M8FLOW_NATS_NOTIFICATIONS_STREAM_NAME") or "M8FLOW_NOTIFICATIONS"


def nats_notifications_subject() -> str:
    """Subject wildcard the notifications stream captures."""
    return _get("M8FLOW_NATS_NOTIFICATIONS_SUBJECT") or "m8flow.notifications.>"


def external_form_link_ttl_seconds() -> int:
    """How long an external-form secure link stays valid, from environment."""
    return int(_get("M8FLOW_EXTERNAL_FORM_LINK_TTL_SECONDS") or "604800")


def notification_max_attempts() -> int:
    """Give up notifying a request after this many failed email attempts."""
    return int(_get("M8FLOW_NOTIFICATION_MAX_ATTEMPTS") or "5")


def notification_sweep_interval_seconds() -> int:
    """How often the notification worker sweeps for missed pending requests."""
    return int(_get("M8FLOW_NOTIFICATION_SWEEP_INTERVAL_SECONDS") or "60")


def notification_sweep_grace_seconds() -> int:
    """Pending rows younger than this are left to the event fast-path before
    the sweep picks them up, so the two never race on fresh rows."""
    return int(_get("M8FLOW_NOTIFICATION_SWEEP_GRACE_SECONDS") or "120")


def app_frontend_base_url() -> str:
    """Base URL of the frontend, used to build invitation accept links.

    Prefers an explicit M8FLOW_FRONTEND_BASE_URL, then the shared public base URL,
    falling back to the local-dev frontend (http://localhost:6841)."""
    raw = _get("M8FLOW_FRONTEND_BASE_URL") or app_public_base_url()
    if not raw:
        return "http://localhost:6841"
    if "://" not in raw:
        raw = "https://" + raw
    return raw.rstrip("/")


def smtp_settings() -> dict:
    """SMTP configuration for outbound invitation email.

    When host is unset, callers fall back to dev mode (log + return the link)."""
    host = _get("M8FLOW_SMTP_HOST")
    port_raw = _get("M8FLOW_SMTP_PORT") or "587"
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 587
    use_tls_raw = (_get("M8FLOW_SMTP_USE_TLS") or "true").lower()
    return {
        "host": host,
        "port": port,
        "username": _get("M8FLOW_SMTP_USERNAME"),
        "password": _get("M8FLOW_SMTP_PASSWORD"),
        "from_address": _get("M8FLOW_SMTP_FROM") or "no-reply@m8flow.local",
        "use_tls": use_tls_raw in ("1", "true", "yes", "on"),
    }
