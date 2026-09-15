"""Injected collaborator Protocols for the pure resolution core (resolve.py).

Two adapters justify each seam: the real Keycloak-Admin-backed ``Directory``
and DB-backed ``TenantRepo`` in production (``canonicalize.DbTenantRepo`` and
a thin wrapper over ``get_auth_provider()``), versus in-memory fakes in tests.
"""

from __future__ import annotations

from typing import Protocol

from m8flow_backend.integrations.auth.base.models import Membership


class Directory(Protocol):
    """Keycloak Admin API membership lookup -- the "the token listing orgs is
    not enough" enrichment source."""

    def list_memberships(self, *, username: str) -> list[Membership]: ...


class TenantRepo(Protocol):
    """DB-backed tenant-identifier canonicalization."""

    def canonical_tenant_id(self, *identifiers: str | None) -> str | None: ...

    def current_identifiers(self, tenant_id: str) -> set[str]: ...

    def slug_for_identifier(self, tenant_identifier: str) -> str | None: ...
