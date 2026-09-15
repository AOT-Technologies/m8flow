"""Optional capability protocols for the auth seam.

Callers must not sniff these with ``hasattr``. Use the typed accessors on
``AuthProvider`` (``user_admin`` / ``tenant_admin`` / ``group_admin`` /
``role_admin`` / ``directory_admin`` / ``provisioning``), which return the
capability or raise ``CapabilityNotSupported``.

Four narrow ABCs (``SupportsUserAdmin``/``SupportsTenantAdmin``/
``SupportsGroupAdmin``/``SupportsRoleAdmin``) replace the single 21-method
``SupportsDirectoryAdmin`` that predates ticket 01's port-surface lock — a
provider that only supports a subset can decline the rest independently.
``SupportsDirectoryAdmin`` survives as a composing aggregate of all four, for
the ~15 existing call sites that need everything and don't care which
narrow capability backs which method (auth-provider-seam wayfinder map,
ticket 13).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from m8flow_backend.integrations.auth.base.models import Group, Membership, Tenant, TenantRef, User


class SupportsUserAdmin(ABC):
    """Realm/shared-directory user lifecycle."""

    @abstractmethod
    def create_user(
        self,
        *,
        username: str,
        authentication_identifier: str,
        email: str | None = None,
        password: str | None = None,
    ) -> User: ...

    @abstractmethod
    def delete_user(self, *, username: str, authentication_identifier: str) -> None: ...


class SupportsTenantAdmin(ABC):
    """Tenant (organization) lifecycle and membership."""

    @abstractmethod
    def add_member(self, *, username: str, tenant_ref: TenantRef) -> Membership: ...

    @abstractmethod
    def remove_member(self, *, username: str, tenant_ref: TenantRef) -> None: ...

    @abstractmethod
    def get_member(self, *, username: str, tenant_ref: TenantRef) -> User: ...

    @abstractmethod
    def list_members(
        self,
        *,
        tenant_ref: TenantRef,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]: ...

    @abstractmethod
    def get_tenant(self, tenant_ref: TenantRef) -> Tenant: ...

    @abstractmethod
    def create_tenant(self, *, alias: str, name: str | None = None) -> Tenant: ...

    @abstractmethod
    def update_tenant(self, tenant_ref: TenantRef, *, name: str) -> Tenant: ...

    @abstractmethod
    def delete_tenant(self, tenant_ref: TenantRef) -> None: ...


class SupportsGroupAdmin(ABC):
    """Tenant-scoped group lifecycle, membership, and role mapping."""

    @abstractmethod
    def list_groups(self, tenant_ref: TenantRef) -> list[Group]: ...

    @abstractmethod
    def create_group(self, tenant_ref: TenantRef, *, identifier: str) -> Group: ...

    @abstractmethod
    def delete_group(self, group: Group) -> None: ...

    @abstractmethod
    def rename_group(self, group: Group, *, identifier: str, roles: list[str] | None = None) -> Group: ...

    @abstractmethod
    def add_group_member(self, group: Group, *, username: str) -> None: ...

    @abstractmethod
    def remove_group_member(self, group: Group, *, username: str) -> None: ...

    @abstractmethod
    def list_group_members(self, group: Group) -> list[User]: ...

    @abstractmethod
    def list_member_groups(self, *, username: str, tenant_ref: TenantRef) -> list[Group]: ...

    @abstractmethod
    def set_group_roles(self, group: Group, *, roles: list[str]) -> Group: ...

    @abstractmethod
    def roles_for_group(self, group: Group) -> list[str]: ...

    @abstractmethod
    def ensure_default_groups(self, tenant_ref: TenantRef) -> list[Group]: ...


class SupportsRoleAdmin(ABC):
    """Tenant-scoped role assignment to a user directly (not via a group)."""

    @abstractmethod
    def assign_roles(self, *, username: str, tenant_ref: TenantRef, roles: list[str]) -> Membership: ...

    @abstractmethod
    def remove_roles(self, *, username: str, tenant_ref: TenantRef, roles: list[str]) -> None: ...


class SupportsDirectoryAdmin(SupportsUserAdmin, SupportsTenantAdmin, SupportsGroupAdmin, SupportsRoleAdmin, ABC):
    """Composing aggregate of all four directory-admin capabilities. A
    provider that can't implement one of the four can't compose this
    aggregate but may still expose the others standalone."""


class SupportsProvisioning(ABC):
    """Tenant-realm and client provisioning. Keycloak-heavy; optional on the seam."""

    @abstractmethod
    def create_tenant_realm(self, tenant_ref: TenantRef, *, display_name: str | None = None) -> Tenant: ...

    @abstractmethod
    def delete_tenant_realm(self, tenant_ref: TenantRef) -> None: ...

    @abstractmethod
    def update_tenant_realm(self, tenant_ref: TenantRef, *, display_name: str) -> Tenant: ...

    @abstractmethod
    def ensure_client_redirect_uri(self, tenant_ref: TenantRef, *, redirect_uri: str) -> None: ...
