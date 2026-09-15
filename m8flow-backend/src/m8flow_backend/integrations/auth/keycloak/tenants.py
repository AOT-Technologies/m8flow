"""Keycloak Organizations Admin API as neutral tenants + memberships.

Group/role mutations live in ``groups.py``; HTTP plumbing lives in
``admin_client.py``. The provider returns Tenant / User / Membership.
"""
from __future__ import annotations

import logging
from typing import Any

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, TenantNotFound, UserNotFound
from m8flow_backend.integrations.auth.base.models import Membership, Tenant, TenantRef, User
from m8flow_backend.integrations.auth.keycloak.admin_client import KeycloakAdminClient
from m8flow_backend.integrations.auth.keycloak.settings import shared_realm_name
from m8flow_backend.integrations.auth.keycloak.directory import fetch_user_representation, user_from_representation

logger = logging.getLogger(__name__)


def tenant_from_representation(payload: dict[str, Any]) -> Tenant:
    tenant_id = payload.get("id")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ProviderUnavailable("Directory tenant is missing an id")
    alias = payload.get("alias")
    name = payload.get("name")
    alias_text = alias.strip() if isinstance(alias, str) and alias.strip() else None
    name_text = name.strip() if isinstance(name, str) and name.strip() else None
    return Tenant(
        ref=TenantRef(id=tenant_id.strip(), alias=alias_text, name=name_text),
        display_name=name_text,
    )


def membership_from_tenant(tenant: Tenant) -> Membership:
    return Membership(tenant_ref=tenant.ref, roles=[], groups=[])


def _membership_with_directory_groups(
    tenant: Tenant,
    user_id: str,
    *,
    admin_token: str | None = None,
) -> Membership:
    """Attach the user's org groups, translated to neutral role names."""
    from m8flow_backend.integrations.auth.keycloak.groups import fetch_member_group_representations
    from m8flow_backend.integrations.auth.keycloak.role_mapping import tenant_roles_for_organization_group

    organization_id = tenant.ref.id
    if not organization_id:
        return membership_from_tenant(tenant)
    try:
        representations = fetch_member_group_representations(
            organization_id,
            user_id,
            admin_token=admin_token,
        )
    except ProviderUnavailable:
        return membership_from_tenant(tenant)

    roles: list[str] = []
    seen: set[str] = set()
    for item in representations:
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        leaf = name.strip().strip("/").split("/")[-1]
        for role in tenant_roles_for_organization_group(leaf):
            if role not in seen:
                seen.add(role)
                roles.append(role)
    return Membership(tenant_ref=tenant.ref, roles=list(roles), groups=list(roles))


def _shared_realm_segments(*segments: str) -> tuple[str, ...]:
    """Organization endpoints all hang off the shared realm's ``organizations`` node."""
    return (shared_realm_name(), "organizations", *segments)


def _tenant_id(tenant_ref: TenantRef) -> str | None:
    if isinstance(tenant_ref.id, str) and tenant_ref.id.strip():
        return tenant_ref.id.strip()
    return None


def _tenant_alias(tenant_ref: TenantRef) -> str | None:
    if isinstance(tenant_ref.alias, str) and tenant_ref.alias.strip():
        return tenant_ref.alias.strip()
    return None


def fetch_organization_representation_by_id(
    organization_id: str,
    *,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    normalized_id = str(organization_id).strip()
    response = KeycloakAdminClient(admin_token=admin_token).get(
        *_shared_realm_segments(normalized_id),
        tolerate=(404,),
        context=f"look up tenant {normalized_id!r}",
    )
    if response.status_code == 404:
        return None
    payload = response.json()
    return payload if isinstance(payload, dict) else None


def fetch_organization_representation_by_alias(
    alias: str,
    *,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    if not alias or not str(alias).strip():
        raise ValueError("alias is required")
    normalized_alias = str(alias).strip()
    client = KeycloakAdminClient(admin_token=admin_token)

    def _load(**params: str) -> list[dict[str, Any]]:
        payload = client.get(
            *_shared_realm_segments(),
            params=params,
            context=f"look up tenant alias {normalized_alias!r}",
        ).json()
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    organizations = _load(search=normalized_alias, exact="true", briefRepresentation="false", max="100")
    if not organizations:
        organizations = _load(search=normalized_alias, exact="false", briefRepresentation="false", max="100")
    if not organizations:
        organizations = _load(briefRepresentation="false", max="100")
    for organization in organizations:
        if organization.get("alias") == normalized_alias:
            return organization
    return None


def resolve_tenant_ref(tenant_ref: TenantRef, *, admin_token: str | None = None) -> Tenant:
    tenant_id = _tenant_id(tenant_ref)
    if tenant_id:
        representation = fetch_organization_representation_by_id(tenant_id, admin_token=admin_token)
        if representation is not None:
            return tenant_from_representation(representation)
    alias = _tenant_alias(tenant_ref)
    if alias:
        representation = fetch_organization_representation_by_alias(alias, admin_token=admin_token)
        if representation is not None:
            return tenant_from_representation(representation)
    raise TenantNotFound(tenant_id or alias or "")


def create_tenant(
    *,
    alias: str,
    name: str | None = None,
    enabled: bool = True,
    admin_token: str | None = None,
) -> Tenant:
    if not alias or not str(alias).strip():
        raise ValueError("alias is required")
    normalized_alias = str(alias).strip()
    display_name = str(name).strip() if name and str(name).strip() else normalized_alias
    client = KeycloakAdminClient(admin_token=admin_token)
    response = client.post(
        *_shared_realm_segments(),
        json={"alias": normalized_alias, "name": display_name, "enabled": enabled},
        tolerate=(409,),
        context=f"create tenant {normalized_alias!r}",
    )
    if response.status_code == 409:
        raise ProviderUnavailable("Tenant already exists")
    # Reuse this operation's resolved token so the follow-up lookups don't re-fetch it.
    token = client.token
    location = response.headers.get("Location")
    representation = None
    if location and isinstance(location, str) and location.strip():
        organization_id = location.strip().rstrip("/").split("/")[-1]
        representation = fetch_organization_representation_by_id(organization_id, admin_token=token)
    if representation is None:
        representation = fetch_organization_representation_by_alias(normalized_alias, admin_token=token)
    if representation is None:
        raise ProviderUnavailable(f"Tenant {normalized_alias!r} was created but could not be fetched")
    return tenant_from_representation(representation)


def update_tenant(
    tenant_ref: TenantRef,
    *,
    name: str,
    enabled: bool = True,
    admin_token: str | None = None,
) -> Tenant:
    if not name or not str(name).strip():
        raise ValueError("name is required")
    tenant = resolve_tenant_ref(tenant_ref, admin_token=admin_token)
    tenant_id = tenant.ref.id
    alias = tenant.ref.alias
    if not tenant_id or not alias:
        raise ProviderUnavailable("Directory tenant is missing id or alias")
    normalized_name = str(name).strip()
    KeycloakAdminClient(admin_token=admin_token).put(
        *_shared_realm_segments(tenant_id),
        json={"id": tenant_id, "alias": alias, "name": normalized_name, "enabled": enabled},
        context=f"update tenant {tenant_id!r}",
    )
    return Tenant(
        ref=TenantRef(id=tenant_id, alias=alias, name=normalized_name),
        display_name=normalized_name,
    )


def delete_tenant(tenant_ref: TenantRef, *, admin_token: str | None = None) -> None:
    try:
        tenant = resolve_tenant_ref(tenant_ref, admin_token=admin_token)
    except TenantNotFound:
        return
    tenant_id = tenant.ref.id
    if not tenant_id:
        raise ProviderUnavailable("Directory tenant is missing an id")
    KeycloakAdminClient(admin_token=admin_token).delete(
        *_shared_realm_segments(tenant_id),
        tolerate=(404,),
        context=f"delete tenant {tenant_id!r}",
    )


def search_member_representations(
    organization_id: str,
    search: str,
    *,
    exact: bool = False,
    admin_token: str | None = None,
    max_results: int = 100,
    first_result: int = 0,
) -> list[dict[str, Any]]:
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    normalized_id = str(organization_id).strip()
    normalized_search = str(search).strip() if isinstance(search, str) else ""
    params: dict[str, Any] = {"max": max_results}
    if first_result > 0:
        params["first"] = first_result
    if normalized_search:
        params["search"] = normalized_search
        params["exact"] = "true" if exact else "false"
    payload = KeycloakAdminClient(admin_token=admin_token).get(
        *_shared_realm_segments(normalized_id, "members"),
        params=params,
        context=f"search members of tenant {normalized_id!r}",
    ).json()
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def fetch_member_representation(
    organization_id: str,
    username: str,
    *,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    if not username or not str(username).strip():
        raise ValueError("username is required")
    normalized_username = str(username).strip()
    members = search_member_representations(
        organization_id,
        normalized_username,
        exact=True,
        admin_token=admin_token,
    )
    if not members:
        members = search_member_representations(
            organization_id,
            normalized_username,
            exact=False,
            admin_token=admin_token,
        )
    exact = [member for member in members if member.get("username") == normalized_username]
    if len(exact) != 1:
        return None
    return exact[0]


def add_member_by_user_id(
    organization_id: str,
    user_id: str,
    *,
    admin_token: str | None = None,
) -> None:
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id is required")
    normalized_id = str(organization_id).strip()
    normalized_user_id = str(user_id).strip()
    response = KeycloakAdminClient(admin_token=admin_token).post(
        *_shared_realm_segments(normalized_id, "members"),
        json=normalized_user_id,
        tolerate=(409,),
        context=f"add member {normalized_user_id!r} to tenant {normalized_id!r}",
    )
    if response.status_code == 409:
        logger.info(
            "User %s is already a member of tenant %s; ignoring conflict.",
            normalized_user_id,
            normalized_id,
        )


def add_member_by_username(
    tenant_ref: TenantRef,
    username: str,
    *,
    admin_token: str | None = None,
) -> Membership:
    tenant = resolve_tenant_ref(tenant_ref, admin_token=admin_token)
    tenant_id = tenant.ref.id
    if not tenant_id:
        raise ProviderUnavailable("Directory tenant is missing an id")
    representation = fetch_user_representation(shared_realm_name(), username, admin_token=admin_token)
    if representation is None:
        raise UserNotFound(username)
    user_id = representation.get("id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ProviderUnavailable("Directory user is missing a subject")
    add_member_by_user_id(tenant_id, user_id, admin_token=admin_token)
    return membership_from_tenant(tenant)


def remove_member_by_user_id(
    organization_id: str,
    member_id: str,
    *,
    admin_token: str | None = None,
) -> None:
    if not organization_id or not str(organization_id).strip():
        raise ValueError("organization_id is required")
    if not member_id or not str(member_id).strip():
        raise ValueError("member_id is required")
    normalized_id = str(organization_id).strip()
    normalized_member_id = str(member_id).strip()
    KeycloakAdminClient(admin_token=admin_token).delete(
        *_shared_realm_segments(normalized_id, "members", normalized_member_id),
        tolerate=(404,),
        context=f"remove member {normalized_member_id!r} from tenant {normalized_id!r}",
    )


def remove_member_by_username(
    tenant_ref: TenantRef,
    username: str,
    *,
    admin_token: str | None = None,
) -> None:
    tenant = resolve_tenant_ref(tenant_ref, admin_token=admin_token)
    tenant_id = tenant.ref.id
    if not tenant_id:
        raise ProviderUnavailable("Directory tenant is missing an id")
    representation = fetch_member_representation(tenant_id, username, admin_token=admin_token)
    if representation is None:
        raise UserNotFound(username)
    member_id = representation.get("id")
    if not isinstance(member_id, str) or not member_id.strip():
        raise ProviderUnavailable("Directory user is missing a subject")
    remove_member_by_user_id(tenant_id, member_id, admin_token=admin_token)


def list_user_organization_representations(
    user_id: str,
    *,
    realm: str | None = None,
    admin_token: str | None = None,
) -> list[dict[str, Any]]:
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id is required")
    normalized_user_id = str(user_id).strip()
    normalized_realm = str(realm).strip() if realm and str(realm).strip() else shared_realm_name()
    # Keycloak 26+ lists a user's orgs at organizations/members/{id}/organizations,
    # not users/{id}/organizations (that path 404s and was treated as zero-org).
    response = KeycloakAdminClient(admin_token=admin_token).get(
        normalized_realm,
        "organizations",
        "members",
        normalized_user_id,
        "organizations",
        tolerate=(404,),
        context=f"list tenants for user {normalized_user_id!r}",
    )
    if response.status_code == 404:
        return []
    payload = response.json()
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def list_memberships_for_username(username: str, *, admin_token: str | None = None) -> list[Membership]:
    representation = fetch_user_representation(shared_realm_name(), username, admin_token=admin_token)
    if representation is None:
        raise UserNotFound(username)
    user_id = representation.get("id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ProviderUnavailable("Directory user is missing a subject")
    organizations = list_user_organization_representations(user_id, admin_token=admin_token)
    return [
        _membership_with_directory_groups(
            tenant_from_representation(item),
            user_id,
            admin_token=admin_token,
        )
        for item in organizations
    ]


def list_members(
    tenant_ref: TenantRef,
    *,
    query: str = "",
    limit: int = 50,
    offset: int = 0,
    admin_token: str | None = None,
) -> list[User]:
    tenant = resolve_tenant_ref(tenant_ref, admin_token=admin_token)
    tenant_id = tenant.ref.id
    if not tenant_id:
        raise ProviderUnavailable("Directory tenant is missing an id")
    representations = search_member_representations(
        tenant_id,
        query,
        exact=False,
        admin_token=admin_token,
        max_results=limit,
        first_result=offset,
    )
    return [user_from_representation(item) for item in representations]


def get_member(tenant_ref: TenantRef, username: str, *, admin_token: str | None = None) -> User:
    tenant = resolve_tenant_ref(tenant_ref, admin_token=admin_token)
    tenant_id = tenant.ref.id
    if not tenant_id:
        raise ProviderUnavailable("Directory tenant is missing an id")
    representation = fetch_member_representation(tenant_id, username, admin_token=admin_token)
    if representation is None:
        raise UserNotFound(username)
    return user_from_representation(representation)
