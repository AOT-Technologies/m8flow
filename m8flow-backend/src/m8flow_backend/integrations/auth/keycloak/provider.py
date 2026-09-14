"""Keycloak realization of ``AuthProvider``, on top of ``OidcAuthProvider``.

Session/OIDC + JWKS ``verify_token`` are inherited (auth-provider-seam
wayfinder map, ticket 04); this module supplies claims mapping, directory
user get/search/create/delete, tenant/membership operations, group/role
mapping, and realm provisioning.
"""
from __future__ import annotations

from typing import Any

from m8flow_backend.integrations.auth.base.capabilities import SupportsDirectoryAdmin, SupportsProvisioning
from m8flow_backend.integrations.auth.base.errors import UserNotFound
from m8flow_backend.integrations.auth.base.models import (
    Group,
    IssuerRef,
    Membership,
    Tenant,
    TenantRef,
    User,
    VerifiedClaims,
)
from m8flow_backend.integrations.auth.base.oidc import OidcAuthProvider
from m8flow_backend.integrations.auth.keycloak import directory, groups, tenants
from m8flow_backend.integrations.auth.keycloak.settings import (
    KeycloakSettings,
    configure,
    current_settings,
    default_organization_alias,
    default_organization_name,
    keycloak_url,
    master_realm_name,
    shared_realm_name,
)
from m8flow_backend.integrations.auth.keycloak.claims import (
    extract_realm_from_issuer,
    realm_name_from_payload,
    verified_claims_from_payload,
)
from m8flow_backend.integrations.auth.keycloak.oidc import oidc_client
from m8flow_backend.integrations.auth.keycloak.provisioning import KeycloakProvisioning


class KeycloakAuthProvider(OidcAuthProvider):
    """Concrete Keycloak provider. Session/OIDC + verify_token are inherited
    from OidcAuthProvider (auth-provider-seam wayfinder map, ticket 04) --
    this class supplies map_claims plus everything Keycloak-specific:
    directory reads, self-description, and the directory-admin/provisioning
    capabilities."""

    def __init__(self, settings: KeycloakSettings | None = None) -> None:
        # Process-global single-active-config: helpers read current_settings(),
        # not per-instance state. configure() rejects a second divergent
        # settings object (see settings.py). Prefer get_auth_provider().
        resolved = settings if settings is not None else KeycloakSettings.from_env()
        configure(resolved)
        super().__init__(oidc_client)

    @property
    def settings(self) -> KeycloakSettings:
        """Active process-wide Keycloak settings (same object helpers use)."""
        return current_settings()

    def map_claims(self, payload: dict[str, Any]) -> VerifiedClaims:
        # ValueError -> TokenInvalid translation happens once, centrally, in
        # OidcAuthProvider.verify_token -- map_claims just maps.
        return verified_claims_from_payload(payload)

    def get_user(self, *, username: str, issuer: IssuerRef) -> User:
        representation = directory.fetch_user_representation(issuer.value, username)
        if representation is None:
            raise UserNotFound(username)
        return directory.user_from_representation(representation)

    def search_users(
        self,
        *,
        query: str,
        issuer: IssuerRef,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        representations = directory.search_user_representations(
            issuer.value,
            query,
            max_results=limit,
            first_result=offset,
        )
        return [directory.user_from_representation(item) for item in representations]

    def list_memberships(self, *, username: str) -> list[Membership]:
        return tenants.list_memberships_for_username(username)

    def set_active_tenant(self, *, username: str, tenant_id: str) -> None:
        # tenant_id is the Keycloak organization id (== the backend tenant id);
        # RealmInfoMapper resolves it via OrganizationProvider.getById, gated by
        # isMember, and emits m8flow_tenant_* + organization.{alias}.{id,name}.
        directory.set_user_attribute(
            shared_realm_name(),
            username,
            name="m8flow_active_tenant",
            value=tenant_id,
        )

    def default_issuer(self) -> IssuerRef:
        return IssuerRef(value=shared_realm_name())

    def default_tenant_ref(self) -> TenantRef:
        return TenantRef(alias=default_organization_alias(), name=default_organization_name())

    def authorization_endpoint_url(self, issuer: IssuerRef) -> str:
        return self._oidc.authorization_endpoint(issuer.value)

    def default_issuer_claim(self) -> str:
        return f"{keycloak_url().rstrip('/')}/realms/{shared_realm_name().strip()}"

    def is_master_issuer(self, claims: VerifiedClaims) -> bool:
        master_realm = master_realm_name()
        authentication_identifier = realm_name_from_payload(claims.jwt_claims)
        issuer_realm = extract_realm_from_issuer(claims.issuer)
        return authentication_identifier == master_realm or issuer_realm == master_realm

    @property
    def user_admin(self) -> SupportsDirectoryAdmin:
        return _KeycloakDirectoryAdmin()

    @property
    def tenant_admin(self) -> SupportsDirectoryAdmin:
        return _KeycloakDirectoryAdmin()

    @property
    def group_admin(self) -> SupportsDirectoryAdmin:
        return _KeycloakDirectoryAdmin()

    @property
    def role_admin(self) -> SupportsDirectoryAdmin:
        return _KeycloakDirectoryAdmin()

    @property
    def directory_admin(self) -> SupportsDirectoryAdmin:
        return _KeycloakDirectoryAdmin()

    @property
    def provisioning(self) -> SupportsProvisioning:
        return KeycloakProvisioning()


class _KeycloakDirectoryAdmin(SupportsDirectoryAdmin):
    """Directory mutations: users, tenants, memberships, and groups. One class
    implementing all four narrow capabilities (SupportsDirectoryAdmin's
    composing aggregate) -- Keycloak supports everything, so there's no
    reason to split the implementation, only the interface (ticket 13)."""

    def create_user(
        self,
        *,
        username: str,
        authentication_identifier: str,
        email: str | None = None,
        password: str | None = None,
    ) -> User:
        return directory.create_user(
            authentication_identifier,
            username,
            password or "",
            email=email,
        )

    def delete_user(self, *, username: str, authentication_identifier: str) -> None:
        directory.delete_user_by_username(authentication_identifier, username)

    def add_member(self, *, username: str, tenant_ref: TenantRef) -> Membership:
        return tenants.add_member_by_username(tenant_ref, username)

    def remove_member(self, *, username: str, tenant_ref: TenantRef) -> None:
        tenants.remove_member_by_username(tenant_ref, username)

    def get_member(self, *, username: str, tenant_ref: TenantRef) -> User:
        return tenants.get_member(tenant_ref, username)

    def list_members(
        self,
        *,
        tenant_ref: TenantRef,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        return tenants.list_members(tenant_ref, query=query, limit=limit, offset=offset)

    def get_tenant(self, tenant_ref: TenantRef) -> Tenant:
        return tenants.resolve_tenant_ref(tenant_ref)

    def create_tenant(self, *, alias: str, name: str | None = None) -> Tenant:
        tenant = tenants.create_tenant(alias=alias, name=name)
        groups.ensure_default_groups(tenant.ref)
        return tenant

    def update_tenant(self, tenant_ref: TenantRef, *, name: str) -> Tenant:
        return tenants.update_tenant(tenant_ref, name=name)

    def delete_tenant(self, tenant_ref: TenantRef) -> None:
        tenants.delete_tenant(tenant_ref)

    def assign_roles(self, *, username: str, tenant_ref: TenantRef, roles: list[str]) -> Membership:
        groups.assign_roles(username=username, tenant_ref=tenant_ref, roles=roles)
        return Membership(tenant_ref=tenant_ref, roles=list(roles), groups=[])

    def remove_roles(self, *, username: str, tenant_ref: TenantRef, roles: list[str]) -> None:
        groups.remove_roles(username=username, tenant_ref=tenant_ref, roles=roles)

    def list_groups(self, tenant_ref: TenantRef) -> list[Group]:
        return groups.list_groups(tenant_ref)

    def create_group(self, tenant_ref: TenantRef, *, identifier: str) -> Group:
        return groups.create_group(tenant_ref, identifier=identifier)

    def delete_group(self, group: Group) -> None:
        groups.delete_group(group)

    def rename_group(self, group: Group, *, identifier: str, roles: list[str] | None = None) -> Group:
        return groups.rename_group(group, identifier=identifier, roles=roles)

    def add_group_member(self, group: Group, *, username: str) -> None:
        groups.add_group_member(group, username=username)

    def remove_group_member(self, group: Group, *, username: str) -> None:
        groups.remove_group_member(group, username=username)

    def list_group_members(self, group: Group) -> list[User]:
        return groups.list_group_members(group)

    def list_member_groups(self, *, username: str, tenant_ref: TenantRef) -> list[Group]:
        return groups.list_member_groups(username=username, tenant_ref=tenant_ref)

    def set_group_roles(self, group: Group, *, roles: list[str]) -> Group:
        return groups.set_group_roles(group, roles=roles)

    def roles_for_group(self, group: Group) -> list[str]:
        return groups.roles_for_group(group)

    def ensure_default_groups(self, tenant_ref: TenantRef) -> list[Group]:
        return groups.ensure_default_groups(tenant_ref)
