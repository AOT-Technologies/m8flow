"""Concrete production adapter for the ``Directory`` port (ports.py). The
``TenantRepo`` production adapter is ``canonicalize.DbTenantRepo`` -- it
stays there since it's a thin wrapper over that module's own query helper.
"""

from __future__ import annotations

from m8flow_backend.integrations.auth.base.models import Membership


class ProviderDirectory:
    """Real ``Directory`` adapter: the configured auth provider's directory
    membership lookup, through ``AuthService`` (honours the opt-in membership
    cache; raises on provider failure so ``resolve`` owns the fallback).

    ``issuer`` is the verified token issuer of the request being resolved; it
    scopes the cache entry (see ``AuthService.membership_cache_scope``).
    Without it the lookup is never cached."""

    def __init__(self, *, issuer: str | None = None) -> None:
        self._issuer = issuer

    def list_memberships(self, *, username: str) -> list[Membership]:
        from m8flow_backend.integrations.auth import get_auth_provider
        from m8flow_backend.integrations.auth.core import AuthService

        return AuthService(get_auth_provider()).directory_memberships(
            username, issuer=self._issuer
        )


#: Former, vendor-named alias kept for existing imports.
KeycloakDirectory = ProviderDirectory
