"""Keycloak settings: typed config resolved once, replacing config.py's
per-call ``os.environ`` reads.

Env keys (``M8FLOW_KEYCLOAK_*`` / legacy ``KEYCLOAK_*``) are unchanged — see
``KeycloakSettings.from_env`` for every fallback/default rule, each carried
over verbatim from the module this replaces.

**Single-active-config (process-global).** Helper modules
(``groups`` / ``tenants`` / ``admin_client`` / ``directory`` / ``oidc``) read
settings only via ``current_settings()`` (and the thin accessor wrappers
below). There is intentionally **one** active ``KeycloakSettings`` per
process — not one per ``KeycloakAuthProvider`` instance. Constructing a
provider calls ``configure()``; a second construction with *different*
settings raises. Identical settings are allowed (tests often build
``KeycloakAuthProvider()`` repeatedly). Call ``reset_keycloak_settings()``
before installing a new config in tests (same teardown pattern as
``reset_jwks_cache()`` / ``reset_auth_provider()``).

``KeycloakAuthProvider.__init__`` (or a test/conformance caller) resolves a
``KeycloakSettings`` and calls ``configure()`` with it. ``current_settings()``
falls back to ``KeycloakSettings.from_env()`` on first use if nothing has
been configured yet — e.g. a test that exercises a module function directly
without constructing a provider first.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_KEYCLOAK_CLIENT_SECRET = "JXeQExm0JhQPLumgHtIIqf52bDalHz0q"
DEFAULT_SHARED_REALM_NAME = "m8flow"
DEFAULT_MASTER_REALM_NAME = "master"

# integrations/auth/keycloak/settings.py -> m8flow_backend/
_M8FLOW_BACKEND_PACKAGE_DIR = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class KeycloakSettings:
    """Fully-resolved Keycloak configuration. Every field mirrors one of
    config.py's former accessor functions, with the exact same fallback and
    default rules — see ``from_env``."""

    keycloak_url: str
    keycloak_public_issuer_base: str
    keycloak_admin_user: str | None
    keycloak_admin_password: str
    shared_realm_name: str
    shared_realm_label: str
    default_organization_alias: str
    default_organization_name: str
    master_realm_name: str
    realm_template_path: str
    keycloak_default_groups_path: str
    spoke_keystore_p12_path: str | None
    spoke_keystore_password: str
    spoke_client_id: str
    spoke_client_secret: str
    master_client_secret: str
    template_realm_name: str

    @classmethod
    def from_env(cls, raw: Mapping[str, str] | None = None) -> KeycloakSettings:
        source: Mapping[str, str] = raw if raw is not None else os.environ

        def _get(key: str, default: str | None = None) -> str | None:
            value = source.get(key)
            if value is not None and value != "":
                return value.strip()
            return default

        keycloak_url = (_get("KEYCLOAK_URL") or _get("M8FLOW_KEYCLOAK_URL") or "http://localhost:6842").rstrip("/")
        keycloak_public_issuer_base = (
            _get("KEYCLOAK_HOSTNAME") or _get("M8FLOW_KEYCLOAK_PUBLIC_ISSUER_BASE") or keycloak_url
        ).rstrip("/")
        shared_realm_name = _get("M8FLOW_KEYCLOAK_SHARED_REALM") or DEFAULT_SHARED_REALM_NAME
        default_organization_alias = _get("M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS") or shared_realm_name
        spoke_client_secret = _get("M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET") or ""

        spoke_keystore_default = "m8flow-backend/keystore.p12"
        raw_p12 = _get("M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12") or spoke_keystore_default
        p12_path = Path(raw_p12)
        if not p12_path.is_absolute():
            p12_path = Path.cwd() / raw_p12

        raw_template_path = _get("M8FLOW_KEYCLOAK_REALM_TEMPLATE_PATH")
        if raw_template_path:
            template_path = Path(raw_template_path)
            if not template_path.is_absolute():
                template_path = Path.cwd() / raw_template_path
        else:
            # Same walk as the former config.py location: m8flow_backend -> src -> m8flow-backend
            root = _M8FLOW_BACKEND_PACKAGE_DIR.parent.parent
            template_path = root / "keycloak" / "realm_exports" / "m8flow-tenant-template.json"

        raw_groups_path = _get("M8FLOW_KEYCLOAK_DEFAULT_GROUPS_PATH")
        if raw_groups_path:
            groups_path = Path(raw_groups_path)
            if not groups_path.is_absolute():
                groups_path = Path.cwd() / raw_groups_path
        else:
            groups_path = _M8FLOW_BACKEND_PACKAGE_DIR / "config" / "keycloak" / "default_groups.json"

        return cls(
            keycloak_url=keycloak_url,
            keycloak_public_issuer_base=keycloak_public_issuer_base,
            keycloak_admin_user=_get("KEYCLOAK_ADMIN_USER") or _get("M8FLOW_KEYCLOAK_ADMIN_USER"),
            keycloak_admin_password=_get("KEYCLOAK_ADMIN_PASSWORD") or _get("M8FLOW_KEYCLOAK_ADMIN_PASSWORD") or "",
            shared_realm_name=shared_realm_name,
            shared_realm_label=(
                "M8Flow Realm" if shared_realm_name == DEFAULT_SHARED_REALM_NAME else shared_realm_name
            ),
            default_organization_alias=default_organization_alias,
            default_organization_name=(
                _get("M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_NAME") or default_organization_alias
            ),
            master_realm_name=_get("M8FLOW_KEYCLOAK_MASTER_REALM") or DEFAULT_MASTER_REALM_NAME,
            realm_template_path=str(template_path),
            keycloak_default_groups_path=str(groups_path),
            spoke_keystore_p12_path=str(p12_path) if p12_path.exists() else None,
            spoke_keystore_password=_get("M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD") or "",
            spoke_client_id=_get("M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID") or "m8flow-backend",
            spoke_client_secret=spoke_client_secret,
            master_client_secret=(
                _get("M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET") or spoke_client_secret or DEFAULT_KEYCLOAK_CLIENT_SECRET
            ),
            template_realm_name=DEFAULT_SHARED_REALM_NAME,
        )


_lock = threading.Lock()
_active: KeycloakSettings | None = None


def configure(settings: KeycloakSettings) -> None:
    """Install the process-wide active settings.

    Called by ``KeycloakAuthProvider.__init__``; tests may call this (or
    construct a provider) after ``reset_keycloak_settings()``.

    Re-entering with the *same* settings is a no-op. Re-entering with
    *different* settings raises ``RuntimeError`` — helpers always read the
    module singleton, so a second provider must not silently rewrite the
    first's effective config. Reset explicitly before swapping.
    """
    global _active
    with _lock:
        if _active is not None and _active != settings:
            raise RuntimeError(
                "Keycloak settings are process-global (single-active-config). "
                "An active KeycloakSettings is already configured; call "
                "reset_keycloak_settings() before installing a different one. "
                "Constructing multiple KeycloakAuthProvider instances with "
                "divergent settings is not supported."
            )
        _active = settings


def current_settings() -> KeycloakSettings:
    """Return the active settings, resolving from the environment on first
    use if nothing has called ``configure()`` yet (e.g. a module function
    exercised directly, without a provider constructed first)."""
    global _active
    if _active is None:
        with _lock:
            if _active is None:
                _active = KeycloakSettings.from_env()
    return _active


def reset_keycloak_settings() -> None:
    """Drop the cached settings so the next ``current_settings()`` /
    ``configure()`` can install a fresh config. Test-only, mirroring
    ``reset_jwks_cache()`` / ``reset_auth_provider()``."""
    global _active
    with _lock:
        _active = None


# --- Back-compat function API -------------------------------------------
# Every former config.py accessor, now a one-line delegation to the active
# KeycloakSettings instead of a per-call os.environ read. Names and
# signatures are unchanged, so callers across the adapter — and the callers
# outside it that tickets 06/07-09 still need to drain onto the port — are
# untouched by this rename beyond their import path.


def keycloak_url() -> str:
    return current_settings().keycloak_url


def keycloak_public_issuer_base() -> str:
    return current_settings().keycloak_public_issuer_base


def keycloak_admin_user() -> str:
    return current_settings().keycloak_admin_user


def keycloak_admin_password() -> str:
    return current_settings().keycloak_admin_password


def shared_realm_name() -> str:
    return current_settings().shared_realm_name


def shared_realm_label() -> str:
    return current_settings().shared_realm_label


def default_organization_alias() -> str:
    return current_settings().default_organization_alias


def default_organization_name() -> str:
    return current_settings().default_organization_name


def master_realm_name() -> str:
    return current_settings().master_realm_name


def realm_template_path() -> str:
    return current_settings().realm_template_path


def keycloak_default_groups_path() -> str:
    return current_settings().keycloak_default_groups_path


def spoke_keystore_p12_path() -> str | None:
    return current_settings().spoke_keystore_p12_path


def spoke_keystore_password() -> str:
    return current_settings().spoke_keystore_password


def spoke_client_id() -> str:
    return current_settings().spoke_client_id


def spoke_client_secret() -> str:
    return current_settings().spoke_client_secret


def master_client_secret() -> str:
    return current_settings().master_client_secret


def template_realm_name() -> str:
    return current_settings().template_realm_name
