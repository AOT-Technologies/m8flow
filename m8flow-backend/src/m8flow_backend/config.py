"""M8Flow host configuration from the environment.

Keycloak accessors live in ``m8flow_backend.integrations.auth.keycloak.settings``.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from pathlib import Path

__all__ = [
    "TRUTHY",
    "app_frontend_base_url",
    "app_public_base_url",
    "external_form_link_ttl_seconds",
    "nats_audit_retention_days",
    "nats_broker_metrics_interval_seconds",
    "nats_enabled",
    "nats_events_stream_name",
    "nats_message_inspection_enabled",
    "nats_message_preview_max_bytes",
    "nats_monitoring_enabled",
    "nats_monitoring_url",
    "nats_notifications_stream_name",
    "nats_notifications_subject",
    "nats_token_salt",
    "nats_url",
    "notification_max_attempts",
    "notification_sweep_grace_seconds",
    "notification_sweep_interval_seconds",
    "redirect_uri_backend_host_and_path",
    "redirect_uri_frontend_host",
    "smtp_settings",
    "vault_addr",
    "vault_approle_mount_point",
    "vault_enabled",
    "vault_mount_point",
    "vault_namespace",
    "vault_role_id",
    "vault_secret_id",
    "vault_secret_path_prefix",
    "vault_tenant_policy_prefix",
    "vault_tenant_role_prefix",
    "vault_tenant_secret_id_num_uses",
    "vault_tenant_secret_id_ttl",
    "vault_tenant_token_max_ttl",
    "vault_tenant_token_ttl",
    "vault_timeout_seconds",
    "vault_token",
    "vault_verify",
]


def _get(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key)
    if value is not None and value != "":
        return value.strip()
    return default


# Spellings an operator may reasonably reach for in a .env, a compose file, or a query
# string. Anything outside this set is false, so a typo fails closed. Public because
# request handlers parse boolean query args against the same vocabulary.
TRUTHY = frozenset({"true", "1", "yes", "on"})


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


def nats_token_salt() -> str:
    return _get("M8FLOW_NATS_TOKEN_SALT") or "m8flow_default_salt"


def nats_url() -> str:
    return _get("M8FLOW_NATS_URL")


def nats_enabled() -> bool:
    """Whether the NATS event-driven integration is switched on."""
    return _env_truthy(_get("M8FLOW_NATS_ENABLED"))


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
    return int(_get("M8FLOW_EXTERNAL_FORM_LINK_TTL_SECONDS") or "604800")


def notification_max_attempts() -> int:
    """Give up notifying a request after this many failed email attempts."""
    return int(_get("M8FLOW_NOTIFICATION_MAX_ATTEMPTS") or "5")


def nats_monitoring_url() -> str:
    """Base URL of the NATS server's monitoring endpoints (/varz, /jsz, /healthz).

    Read by the backend over the internal network, so this port never needs to be
    reachable from a browser.
    """
    return _get("M8FLOW_NATS_MONITORING_URL") or "http://nats:8222"


def nats_monitoring_enabled() -> bool:
    """Whether the NATS monitoring dashboard is switched on.

    Follows M8FLOW_NATS_ENABLED unless overridden: monitoring a disabled subsystem is
    never useful.
    """
    raw = _get("M8FLOW_NATS_MONITORING_ENABLED")
    return nats_enabled() if raw is None else _env_truthy(raw)


def nats_message_inspection_enabled() -> bool:
    """Whether raw message payloads may be read through the monitoring API.

    Off by default: payloads carry tenant business data and m8flow's streams retain
    them indefinitely.
    """
    return _env_truthy(_get("M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED"))


def nats_message_preview_max_bytes() -> int:
    """Cap on how much of a message payload a preview returns."""
    return int(_get("M8FLOW_NATS_MESSAGE_PREVIEW_MAX_BYTES") or "4096")


def nats_audit_retention_days() -> int:
    """How long terminal NATS event-audit rows are kept; 0 or negative disables pruning."""
    return int(_get("M8FLOW_NATS_AUDIT_RETENTION_DAYS") or "90")


def nats_broker_metrics_interval_seconds() -> int:
    """How often m8flow-nats-consumer polls the broker to emit stream/consumer OTel gauges.

    A gauge is last-value-wins per export tick, so polling faster than about half of
    OTEL_METRIC_EXPORT_INTERVAL buys nothing.
    """
    return int(_get("M8FLOW_NATS_BROKER_METRICS_INTERVAL_SECONDS") or "20")


def notification_sweep_interval_seconds() -> int:
    """How often the notification worker sweeps for missed pending requests."""
    return int(_get("M8FLOW_NOTIFICATION_SWEEP_INTERVAL_SECONDS") or "60")


def notification_sweep_grace_seconds() -> int:
    """Pending rows younger than this are left to the event fast-path before
    the sweep picks them up, so the two never race on fresh rows."""
    return int(_get("M8FLOW_NOTIFICATION_SWEEP_GRACE_SECONDS") or "120")


def app_frontend_base_url() -> str:
    """Origin of m8flow-designer, used to build invitation accept links.

    Prefers ``M8FLOW_FRONTEND_BASE_URL``, then ``M8FLOW_APP_PUBLIC_BASE_URL`` when
    that is the user-facing app origin. Does not use Keycloak hostnames — those
    would send invitees to the IdP. Local default is designer at
    ``http://localhost:6853``.
    """
    raw = _get("M8FLOW_FRONTEND_BASE_URL") or _get("M8FLOW_APP_PUBLIC_BASE_URL")
    if not raw:
        return "http://localhost:6853"
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


def _env_truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in TRUTHY


def _read_secret_file(path: str | None) -> str | None:
    if not path:
        return None
    try:
        text = Path(path).expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def vault_enabled() -> bool:
    return _env_truthy(_get("M8FLOW_VAULT_ENABLED"))


def vault_addr() -> str | None:
    return _get("M8FLOW_VAULT_ADDR") or _get("VAULT_ADDR")


def vault_token() -> str | None:
    return (
        _get("M8FLOW_VAULT_TOKEN")
        or _get("VAULT_TOKEN")
        or _read_secret_file(_get("M8FLOW_VAULT_TOKEN_FILE") or _get("VAULT_TOKEN_FILE"))
    )


def vault_role_id() -> str | None:
    return (
        _get("M8FLOW_VAULT_ROLE_ID")
        or _get("VAULT_ROLE_ID")
        or _read_secret_file(_get("M8FLOW_VAULT_ROLE_ID_FILE") or _get("VAULT_ROLE_ID_FILE"))
    )


def vault_secret_id() -> str | None:
    return (
        _get("M8FLOW_VAULT_SECRET_ID")
        or _get("VAULT_SECRET_ID")
        or _read_secret_file(_get("M8FLOW_VAULT_SECRET_ID_FILE") or _get("VAULT_SECRET_ID_FILE"))
    )


def vault_namespace() -> str | None:
    return _get("M8FLOW_VAULT_NAMESPACE") or _get("VAULT_NAMESPACE")


def vault_mount_point() -> str:
    return _get("M8FLOW_VAULT_MOUNT_POINT") or "kv"


def vault_secret_path_prefix() -> str:
    return _get("M8FLOW_VAULT_SECRET_PATH_PREFIX") or "m8flow"


def vault_approle_mount_point() -> str:
    return _get("M8FLOW_VAULT_APPROLE_MOUNT_POINT") or "approle"


def vault_tenant_policy_prefix() -> str:
    return _get("M8FLOW_VAULT_TENANT_POLICY_PREFIX") or "m8flow-tenant-policy"


def vault_tenant_role_prefix() -> str:
    return _get("M8FLOW_VAULT_TENANT_ROLE_PREFIX") or "m8flow-tenant-role"


def vault_tenant_secret_id_num_uses() -> int:
    raw = _get("M8FLOW_VAULT_TENANT_SECRET_ID_NUM_USES") or "1"
    try:
        return max(0, int(raw))
    except ValueError:
        return 1


def vault_tenant_secret_id_ttl() -> str:
    return _get("M8FLOW_VAULT_TENANT_SECRET_ID_TTL") or "10m"


def vault_tenant_token_ttl() -> str:
    return _get("M8FLOW_VAULT_TENANT_TOKEN_TTL") or "10m"


def vault_tenant_token_max_ttl() -> str:
    return _get("M8FLOW_VAULT_TENANT_TOKEN_MAX_TTL") or "30m"


def vault_timeout_seconds() -> float:
    raw = _get("M8FLOW_VAULT_TIMEOUT_SECONDS") or "5"
    try:
        return float(raw)
    except ValueError:
        return 5.0


def vault_verify() -> bool | str:
    ca_cert = _get("M8FLOW_VAULT_CACERT") or _get("VAULT_CACERT")
    if ca_cert:
        path = Path(ca_cert)
        return str(path if path.is_absolute() else Path.cwd() / path)
    if _env_truthy(_get("M8FLOW_VAULT_SKIP_VERIFY") or _get("VAULT_SKIP_VERIFY")):
        return False
    return True
