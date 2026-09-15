"""Concrete production adapter for the ``Directory`` port (ports.py). The
``TenantRepo`` production adapter is ``canonicalize.DbTenantRepo`` -- it
stays there since it's a thin wrapper over that module's own query helper.
"""

from __future__ import annotations

from m8flow_backend.integrations.auth.base.models import Membership


class KeycloakDirectory:
    """Real ``Directory`` adapter: Keycloak Admin API membership lookup via
    the configured auth provider."""

    def list_memberships(self, *, username: str) -> list[Membership]:
        from m8flow_backend.integrations.auth import get_auth_provider

        return get_auth_provider().list_memberships(username=username)
