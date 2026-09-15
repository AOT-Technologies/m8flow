"""Resolve the active ``AuthProvider`` from configuration.

Selection key: ``M8FLOW_AUTH_PROVIDER`` (default ``keycloak``). A second
implementation registers with ``register_auth_provider``; call sites keep
using ``get_auth_provider()``.

The process holds one instance (lazy singleton). Request-time code and
non-request bootstrap both need the provider, and today's Keycloak access is
already process-global env-driven functions — a Flask app-context accessor
would force an app context on paths that don't have one. Tests call
``reset_auth_provider()``.

Registered factories receive the neutral ``AuthSettings`` envelope (see
``integrations.auth.settings``), not raw environment access — they convert
it into their own typed settings before constructing. ``get_auth_provider()``
itself stays zero-arg: it resolves ``AuthSettings.from_env()`` internally, so
none of this module's ~20 existing call sites change.
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from m8flow_backend.integrations.auth.base.errors import AuthProviderError
from m8flow_backend.integrations.auth.base.provider import AuthProvider
from m8flow_backend.integrations.auth.settings import AUTH_PROVIDER_ENV, DEFAULT_AUTH_PROVIDER, AuthSettings

__all__ = [
    "AUTH_PROVIDER_ENV",
    "DEFAULT_AUTH_PROVIDER",
    "get_auth_provider",
    "register_auth_provider",
    "reset_auth_provider",
]

_registry: dict[str, Callable[[AuthSettings], AuthProvider]] = {}
_instance: AuthProvider | None = None
_lock = threading.Lock()
_builtins_registered = False


def register_auth_provider(name: str, factory: Callable[[AuthSettings], AuthProvider]) -> None:
    """Register (or replace) a provider factory under ``name``. ``factory``
    receives the neutral ``AuthSettings`` envelope and converts it into its
    own typed settings before constructing the provider."""
    key = name.strip().lower()
    if not key:
        raise AuthProviderError("Auth provider name must be non-empty")
    _registry[key] = factory


def reset_auth_provider() -> None:
    """Drop the cached instance so the next ``get_auth_provider()`` rebuilds it.

    Also clears Keycloak's process-global settings cache when the Keycloak
    package is importable, so a rebuilt provider can ``configure()`` cleanly.
    """
    global _instance
    with _lock:
        _instance = None
    try:
        from m8flow_backend.integrations.auth.keycloak.settings import reset_keycloak_settings

        reset_keycloak_settings()
    except ImportError:
        pass


def get_auth_provider() -> AuthProvider:
    """Return the process-wide active provider, creating it on first use."""
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is None:
            _instance = _build_auth_provider()
        return _instance


def _ensure_builtins() -> None:
    global _builtins_registered
    if _builtins_registered:
        return
    from m8flow_backend.integrations.auth.keycloak.provider import KeycloakAuthProvider
    from m8flow_backend.integrations.auth.keycloak.settings import KeycloakSettings

    def _build_keycloak_provider(settings: AuthSettings) -> AuthProvider:
        return KeycloakAuthProvider(KeycloakSettings.from_env(settings.raw))

    register_auth_provider(DEFAULT_AUTH_PROVIDER, _build_keycloak_provider)
    _builtins_registered = True


def _build_auth_provider() -> AuthProvider:
    _ensure_builtins()
    settings = AuthSettings.from_env()
    factory = _registry.get(settings.provider)
    if factory is None:
        known = ", ".join(sorted(_registry)) or "(none)"
        raise AuthProviderError(f"Unknown auth provider {settings.provider!r}. Registered: {known}")
    return factory(settings)
