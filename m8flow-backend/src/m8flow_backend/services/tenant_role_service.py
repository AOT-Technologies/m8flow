from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from m8flow_backend.services.keycloak_service import (
    DEFAULT_ORGANIZATION_ROLE_GROUP_NAMES,
    add_organization_group_member,
    get_organization_by_id,
    get_organization_by_alias,
    get_organization_member_by_username,
    get_organization_member_groups,
    remove_organization_group_member,
    search_organization_members,
)
from m8flow_backend.services.authorization_service_patch import _permission_scope_tenant
from m8flow_backend.services.tenant_identity_helpers import (
    qualify_group_identifier,
    upsert_local_shared_realm_member,
)
from m8flow_backend.services.tenant_service import TenantService
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.user_group_assignment import UserGroupAssignmentModel
from spiffworkflow_backend.services.authorization_service import AuthorizationService
from spiffworkflow_backend.services.user_service import UserService


VALID_TENANT_ROLE_NAMES = frozenset(DEFAULT_ORGANIZATION_ROLE_GROUP_NAMES)


def _normalize_role_name(role_name: str) -> str:
    normalized_role_name = str(role_name or "").strip()
    if normalized_role_name not in VALID_TENANT_ROLE_NAMES:
        raise ApiError(
            error_code="invalid_role",
            message=f"Role '{role_name}' is not a supported tenant role.",
            status_code=400,
        )
    return normalized_role_name


def _organization_for_tenant(tenant_id: str) -> tuple[Any, dict[str, Any], str]:
    tenant = TenantService.get_tenant_by_id(tenant_id)
    organization = None

    tenant_identifier = tenant.id.strip() if isinstance(tenant.id, str) and tenant.id.strip() else ""
    if tenant_identifier:
        organization = get_organization_by_id(tenant_identifier)

    if not isinstance(organization, dict):
        tenant_alias = tenant.slug.strip() if isinstance(tenant.slug, str) and tenant.slug.strip() else ""
        if tenant_alias:
            organization = get_organization_by_alias(tenant_alias)

    if not isinstance(organization, dict):
        raise ApiError(
            error_code="organization_not_found",
            message=(
                f"Organization for tenant '{tenant_identifier or tenant_id}'"
                f"{f' (alias: {tenant.slug})' if getattr(tenant, 'slug', None) else ''}"
                " could not be found in Keycloak."
            ),
            status_code=404,
        )

    organization_id = organization.get("id")
    if not isinstance(organization_id, str) or not organization_id.strip():
        raise ApiError(
            error_code="organization_not_found",
            message=(
                f"Organization for tenant '{tenant_identifier or tenant_id}'"
                f"{f' (alias: {tenant.slug})' if getattr(tenant, 'slug', None) else ''}"
                " does not have a valid Keycloak id."
            ),
            status_code=404,
        )
    return tenant, organization, organization_id.strip()


def _normalized_member_roles(organization_id: str, member_id: str) -> list[str]:
    roles: set[str] = set()
    for group in get_organization_member_groups(organization_id, member_id):
        group_name = group.get("name")
        if not isinstance(group_name, str):
            continue
        normalized_group_name = group_name.strip()
        if normalized_group_name in VALID_TENANT_ROLE_NAMES:
            roles.add(normalized_group_name)
    return sorted(roles)


def _serialize_member(
    member: Mapping[str, Any],
    *,
    roles: list[str],
) -> dict[str, Any]:
    first_name = member.get("firstName")
    last_name = member.get("lastName")
    full_name_parts = [
        value.strip()
        for value in (first_name, last_name)
        if isinstance(value, str) and value.strip()
    ]
    display_name = " ".join(full_name_parts) if full_name_parts else None

    return {
        "id": member.get("id"),
        "username": member.get("username"),
        "email": member.get("email"),
        "display_name": display_name,
        "roles": roles,
    }


def _tenant_role_group(role_name: str, tenant_id: str) -> Any:
    group_identifier = qualify_group_identifier(role_name, tenant_id=tenant_id)
    return UserService.find_or_create_group(group_identifier, source_is_open_id=True)


def _local_assignment_query(user: Any, group: Any, tenant_id: str):
    query = UserGroupAssignmentModel.query.filter_by(user_id=user.id, group_id=group.id)
    if hasattr(UserGroupAssignmentModel, "m8f_tenant_id"):
        query = query.filter_by(m8f_tenant_id=tenant_id)
    return query


def _ensure_local_assignment(user: Any, group: Any, tenant_id: str) -> bool:
    assignment = _local_assignment_query(user, group, tenant_id).first()
    if assignment is not None:
        return False

    kwargs: dict[str, Any] = {"user_id": user.id, "group_id": group.id}
    if hasattr(UserGroupAssignmentModel, "m8f_tenant_id"):
        kwargs["m8f_tenant_id"] = tenant_id
    db.session.add(UserGroupAssignmentModel(**kwargs))
    db.session.commit()
    return True


def _ensure_tenant_yaml_permissions_and_everybody_membership(user: Any, tenant_id: str) -> None:
    """
    Ensure the user is enrolled in the tenant's "everybody" group with YAML permissions applied.

    `assign_tenant_role` only writes the requested role group (e.g. ":editor").
    Without this step the tenant's ":everybody" group is never created and the user
    cannot reach permissions like /onboarding, /extensions, /active-users, etc. that
    SpiffWorkflow grants to every signed-in user.  Run the YAML import inside the
    target tenant's permission scope so groups and permissions are tenant-qualified.
    """
    with _permission_scope_tenant(tenant_id):
        AuthorizationService.import_permissions_from_yaml_file(user)


def _delete_local_assignment(user: Any, group: Any, tenant_id: str) -> bool:
    assignment = _local_assignment_query(user, group, tenant_id).first()
    if assignment is None:
        return False
    db.session.delete(assignment)
    db.session.commit()
    return True


def list_tenant_members_with_roles(
    tenant_id: str,
    *,
    search: str | None = None,
    max_results: int = 100,
) -> list[dict[str, Any]]:
    """Return organization members for one tenant with their org-local tenant roles."""
    _tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    members = search_organization_members(
        organization_id,
        search or "",
        exact=False,
        max_results=max_results,
    )

    serialized_members: list[dict[str, Any]] = []
    for member in members:
        member_id = member.get("id")
        username = member.get("username")
        if not isinstance(member_id, str) or not member_id.strip():
            continue
        if not isinstance(username, str) or not username.strip():
            continue
        serialized_members.append(
            _serialize_member(
                member,
                roles=_normalized_member_roles(organization_id, member_id.strip()),
            )
        )

    serialized_members.sort(key=lambda item: str(item.get("username") or ""))
    return serialized_members


def assign_tenant_role(tenant_id: str, username: str, role_name: str) -> dict[str, Any]:
    """Assign one tenant-scoped role to one organization member and mirror it locally."""
    normalized_role_name = _normalize_role_name(role_name)
    tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    member = get_organization_member_by_username(organization_id, username)
    if not isinstance(member, dict):
        raise ApiError(
            error_code="tenant_member_not_found",
            message=f"User '{username}' is not a member of organization '{tenant.slug}'.",
            status_code=404,
        )

    member_id = member.get("id")
    if not isinstance(member_id, str) or not member_id.strip():
        raise ApiError(
            error_code="tenant_member_not_found",
            message=f"User '{username}' does not have a valid Keycloak membership id.",
            status_code=400,
        )

    add_organization_group_member(organization_id, normalized_role_name, member_id.strip())

    local_user = upsert_local_shared_realm_member(member)
    if local_user is None:
        raise ApiError(
            error_code="local_user_sync_failed",
            message=(
                f"User '{username}' was updated in Keycloak, but the local M8Flow user row "
                "could not be created or refreshed."
            ),
            status_code=409,
        )

    group = _tenant_role_group(normalized_role_name, tenant.id)
    assignment_created = _ensure_local_assignment(local_user, group, tenant.id)
    if assignment_created:
        UserService.update_human_task_assignments_for_user(
            local_user,
            new_group_ids={group.id},
            old_group_ids=set(),
        )

    # Ensure the tenant's "everybody" group exists, has its YAML permissions, and
    # the user is enrolled in it. Without this the user only gets the explicit
    # role group and is denied basic SpiffWorkflow endpoints (/onboarding, etc.).
    _ensure_tenant_yaml_permissions_and_everybody_membership(local_user, tenant.id)

    current_roles = _normalized_member_roles(organization_id, member_id.strip())
    updated_roles = sorted(set(current_roles).union({normalized_role_name}))
    return _serialize_member(
        member,
        roles=updated_roles,
    )


def remove_tenant_role(tenant_id: str, username: str, role_name: str) -> dict[str, Any]:
    """Remove one tenant-scoped role from one organization member and mirror it locally."""
    normalized_role_name = _normalize_role_name(role_name)
    tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    member = get_organization_member_by_username(organization_id, username)
    if not isinstance(member, dict):
        raise ApiError(
            error_code="tenant_member_not_found",
            message=f"User '{username}' is not a member of organization '{tenant.slug}'.",
            status_code=404,
        )

    member_id = member.get("id")
    if not isinstance(member_id, str) or not member_id.strip():
        raise ApiError(
            error_code="tenant_member_not_found",
            message=f"User '{username}' does not have a valid Keycloak membership id.",
            status_code=400,
        )

    remove_organization_group_member(organization_id, normalized_role_name, member_id.strip())

    local_user = upsert_local_shared_realm_member(member)
    if local_user is not None:
        group = _tenant_role_group(normalized_role_name, tenant.id)
        assignment_deleted = _delete_local_assignment(local_user, group, tenant.id)
        if assignment_deleted:
            UserService.update_human_task_assignments_for_user(
                local_user,
                new_group_ids=set(),
                old_group_ids={group.id},
            )

    current_roles = _normalized_member_roles(organization_id, member_id.strip())
    updated_roles = sorted(role for role in current_roles if role != normalized_role_name)
    return _serialize_member(
        member,
        roles=updated_roles,
    )
