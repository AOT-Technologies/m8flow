"""M8Flow Keycloak configuration from environment."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


def _get(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key)
    if value is not None and value != "":
        return value.strip()
    return default


def keycloak_url() -> str:
    """Keycloak base URL (no trailing slash)."""
    url = _get("KEYCLOAK_URL") or _get("M8FLOW_KEYCLOAK_URL") or "http://localhost:7002"
    return url.rstrip("/")


def keycloak_public_issuer_base() -> str:
    """Base URL Keycloak uses for the iss claim in tokens (same as KC_HOSTNAME).
    When this differs from keycloak_url() (e.g. Docker proxy), set KEYCLOAK_HOSTNAME or
    M8FLOW_KEYCLOAK_PUBLIC_ISSUER_BASE so the backend accepts the token issuer."""
    url = _get("KEYCLOAK_HOSTNAME") or _get("M8FLOW_KEYCLOAK_PUBLIC_ISSUER_BASE") or keycloak_url()
    return url.rstrip("/")


def keycloak_admin_user() -> str:
    """Master realm admin username (default: superadmin, created by Keycloak entrypoint)."""
    return _get("KEYCLOAK_ADMIN_USER") or _get("M8FLOW_KEYCLOAK_ADMIN_USER") or "superadmin"


def keycloak_admin_password() -> str:
    """Master realm admin password (from env only)."""
    return _get("KEYCLOAK_ADMIN_PASSWORD") or _get("M8FLOW_KEYCLOAK_ADMIN_PASSWORD") or ""


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
    default = _root / "keycloak" / "realm_exports" / "spiffworkflow-realm.json"
    return str(default)


def spoke_keystore_p12_path() -> str | None:
    """Path to PKCS#12 keystore for spoke realm client auth."""
    default = "extensions/m8flow-backend/keystore.p12"
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
    return _get("M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID") or "spiffworkflow-backend"


def spoke_client_secret() -> str:
    """Client secret for spoke realm client (from env only). Set M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET when using client-secret auth."""
    return _get("M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET") or ""


def template_realm_name() -> str:
    """Realm name in the template (for substitution)."""
    return "spiffworkflow"


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
