"""M8Flow host configuration from the environment.

Keycloak accessors live in ``m8flow_backend.integrations.auth.keycloak.settings``.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from pathlib import Path

logger = logging.getLogger(__name__)

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
    "nats_trigger_signing_salt",
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
    """Peppers stored NATS API-key hashes. The fallback keeps keys issued without a salt
    valid; trigger signing uses nats_trigger_signing_salt(), which has none."""
    return _get("M8FLOW_NATS_TOKEN_SALT") or "m8flow_default_salt"


# Salts published in this repo (the code default, sample.env, the consumer README): anyone
# can read them, so they must never sign a trigger event (M8F-574 review).
_PUBLIC_NATS_SALTS = frozenset({"m8flow_default_salt", "changeme_nats_salt", "my-random-salt-string"})
# Signed events sit on the broker, so a short salt can be brute-forced offline from one of
# them. 32 characters is half of the documented `openssl rand -hex 32`.
_MIN_NATS_SIGNING_SALT_LENGTH = 32


def nats_trigger_signing_salt() -> str | None:
    """M8FLOW_NATS_TOKEN_SALT for signing trigger events, or None while it is unset, a
    published placeholder, or too short to resist offline guessing. The signature is all
    that stops a broker client from starting a process as any key's owner, so there is no
    fallback."""
    salt = _get("M8FLOW_NATS_TOKEN_SALT")
    if salt is None or salt in _PUBLIC_NATS_SALTS or len(salt) < _MIN_NATS_SIGNING_SALT_LENGTH:
        return None
    return salt


def nats_trigger_max_age_seconds() -> int:
    """How far a signed trigger event's issued_at may be from the consumer's clock. Older
    events are refused as possible replays, so triggers queued through a consumer outage
    longer than this are dropped (and recorded in the event audit).

    Raises ValueError on anything but a positive whole number of seconds: a negative value
    would refuse every trigger, and a non-number would fail each message instead of boot.
    The trigger consumer reads it at startup so a bad value stops it there."""
    raw = _get("M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS") or "300"
    if not raw.isdecimal() or int(raw) <= 0:
        raise ValueError(f"M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS must be a positive whole number of seconds, got {raw!r}")
    return int(raw)


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


def mcp_server_url() -> str:
    """Streamable-http endpoint of the m8flow-mcp server (must end in /mcp) that the
    MCP Tools proxy dials.

    ``M8FLOW_MCP_SERVER_URL`` is the browser-facing URL the designer bakes into the MCP
    Connection page. ``M8FLOW_MCP_SERVER_INTERNAL_URL`` is a DEVELOPMENT-ONLY, backend-only
    override for local Docker, where that URL is not reachable from the backend container
    (``localhost`` must become ``host.docker.internal``); deployed environments leave it
    unset. Empty when neither is set -- callers report "not configured" rather than
    guessing a default host.
    """
    url = _get("M8FLOW_MCP_SERVER_INTERNAL_URL") or _get("M8FLOW_MCP_SERVER_URL")
    return url.rstrip("/") if url else ""


def nats_monitoring_enabled() -> bool:
    """Whether the NATS monitoring dashboard is switched on.

    Follows M8FLOW_NATS_ENABLED unless overridden: monitoring a disabled subsystem is
    never useful.
    """
    raw = _get("M8FLOW_NATS_MONITORING_ENABLED")
    return nats_enabled() if raw is None else _env_truthy(raw)


def celery_monitoring_enabled() -> bool:
    """Whether the Celery monitoring page is switched on.

    Follows M8FLOW_BACKEND_CELERY_ENABLED unless overridden, as NATS monitoring follows
    M8FLOW_NATS_ENABLED.
    """
    raw = _get("M8FLOW_BACKEND_CELERY_MONITORING_ENABLED")
    return _env_truthy(_get("M8FLOW_BACKEND_CELERY_ENABLED")) if raw is None else _env_truthy(raw)


def celery_task_history_enabled() -> bool:
    """Whether workers record task lifecycle into ``m8flow_celery_task``.

    Follows celery_monitoring_enabled() unless overridden.
    """
    raw = _get("M8FLOW_BACKEND_CELERY_TASK_HISTORY_ENABLED")
    return celery_monitoring_enabled() if raw is None else _env_truthy(raw)


DEFAULT_CELERY_TASK_HISTORY_RETENTION_DAYS = 7


def celery_task_history_retention_days() -> int:
    """How long task history rows are kept; 0 or negative keeps them forever."""
    raw = _get("M8FLOW_BACKEND_CELERY_TASK_HISTORY_RETENTION_DAYS")
    if raw is None or raw == "":
        return DEFAULT_CELERY_TASK_HISTORY_RETENTION_DAYS
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid M8FLOW_BACKEND_CELERY_TASK_HISTORY_RETENTION_DAYS value %r; "
            "falling back to default of %d days",
            raw,
            DEFAULT_CELERY_TASK_HISTORY_RETENTION_DAYS,
        )
        return DEFAULT_CELERY_TASK_HISTORY_RETENTION_DAYS


def celery_worker_state_db() -> str | None:
    """File where a Celery worker keeps its revoked-task list across restarts (Celery's
    worker_state_db, the same as --statedb). Unset keeps revokes in memory only, so a
    restarted worker runs tasks revoked before it stopped."""
    return _get("M8FLOW_BACKEND_CELERY_WORKER_STATE_DB")


def celery_control_enabled() -> bool:
    """Whether the Celery page's control actions (revoke, limits, pool, consumers,
    shutdown) are allowed. Super-admin only either way; follows
    celery_monitoring_enabled() unless overridden."""
    raw = _get("M8FLOW_BACKEND_CELERY_CONTROL_ENABLED")
    return celery_monitoring_enabled() if raw is None else _env_truthy(raw)


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
    """TLS verification for Vault: a CA bundle path, else the system trust store.

    Certificate checks are never disabled. ``*_VAULT_SKIP_VERIFY`` is ignored (with a
    warning); point ``M8FLOW_VAULT_CACERT`` / ``VAULT_CACERT`` at the Vault CA instead,
    including for self-signed dev/QA Vaults.
    """
    ca_cert = _get("M8FLOW_VAULT_CACERT") or _get("VAULT_CACERT")
    if ca_cert:
        path = Path(ca_cert)
        return str(path if path.is_absolute() else Path.cwd() / path)
    if _env_truthy(_get("M8FLOW_VAULT_SKIP_VERIFY") or _get("VAULT_SKIP_VERIFY")):
        logging.getLogger(__name__).warning(
            "VAULT_SKIP_VERIFY is no longer supported and is ignored; set "
            "M8FLOW_VAULT_CACERT to the Vault CA instead."
        )
    return True
