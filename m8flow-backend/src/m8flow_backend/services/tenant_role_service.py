from __future__ import annotations

import re
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from m8flow_backend.services.keycloak_service import (
    add_organization_member,
    add_organization_group_member,
    create_organization_group,
    get_master_admin_token,
    get_organization_by_id,
    get_organization_by_alias,
    get_organization_group_by_id,
    get_organization_member_by_username,
    get_organization_member_groups,
    get_realm_user_by_username,
    list_organization_group_members,
    list_organization_groups,
    organization_group_role_names,
    remove_organization_group_member,
    search_realm_users,
    search_organization_members,
    set_organization_group_role_names,
    shared_realm_name,
)
from m8flow_backend.services.authorization_service_patch import _permission_scope_tenant
from m8flow_backend.services.tenant_group_mapping import (
    VALID_TENANT_ROLE_NAMES,
    organization_group_name_candidates_for_tenant_role,
)
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

TENANT_GROUP_NAME_MAX_LENGTH = 64
TENANT_GROUP_NAME_ALLOWED_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9])?$")
MAX_PARALLEL_KEYCLOAK_LOOKUPS = 8


def _normalize_role_name(role_name: str) -> str:
    normalized_role_name = str(role_name or "").strip()
    if normalized_role_name not in VALID_TENANT_ROLE_NAMES:
        raise ApiError(
            error_code="invalid_role",
            message=f"Role '{role_name}' is not a supported tenant role.",
            status_code=400,
        )
    return normalized_role_name


def _organization_for_tenant(
    tenant_id: str,
    *,
    admin_token: str | None = None,
) -> tuple[Any, dict[str, Any], str]:
    tenant = TenantService.get_tenant_by_id(tenant_id)
    organization = None

    tenant_identifier = tenant.id.strip() if isinstance(tenant.id, str) and tenant.id.strip() else ""
    if tenant_identifier:
        organization = get_organization_by_id(tenant_identifier, admin_token=admin_token)

    if not isinstance(organization, dict):
        tenant_alias = tenant.slug.strip() if isinstance(tenant.slug, str) and tenant.slug.strip() else ""
        if tenant_alias:
            organization = get_organization_by_alias(tenant_alias, admin_token=admin_token)

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


def _role_lookup_key(value: str | None) -> str:
    normalized_value = _normalize_group_name(value)
    return normalized_value.casefold() if normalized_value else ""


def _mapped_roles_from_group(group: Mapping[str, Any] | None) -> list[str]:
    return list(organization_group_role_names(group))


def _organization_group_role_lookup(
    organization_id: str,
    *,
    admin_token: str | None = None,
    groups: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, list[str]]]:
    roles_by_group_id: dict[str, list[str]] = {}
    roles_by_group_name: dict[str, list[str]] = {}

    organization_groups = groups or list_organization_groups(
        organization_id,
        admin_token=admin_token,
        brief_representation=False,
    )

    for group in organization_groups:
        group_id = group.get("id")
        group_name = group.get("name")
        if not isinstance(group_name, str) or not group_name.strip():
            continue

        effective_group = (
            get_organization_group_by_id(
                organization_id,
                group_id.strip(),
                admin_token=admin_token,
            )
            if "attributes" not in group and isinstance(group_id, str) and group_id.strip()
            else None
        ) or group
        mapped_roles = _mapped_roles_from_group(effective_group)

        group_name_key = _role_lookup_key(group_name)
        if group_name_key:
            roles_by_group_name[group_name_key] = mapped_roles
        if isinstance(group_id, str) and group_id.strip():
            roles_by_group_id[group_id.strip()] = mapped_roles

    return {
        "by_group_id": roles_by_group_id,
        "by_group_name": roles_by_group_name,
    }


def _roles_for_group(
    group: Mapping[str, Any],
    *,
    organization_id: str | None = None,
    group_role_lookup: dict[str, dict[str, list[str]]] | None = None,
    admin_token: str | None = None,
) -> list[str]:
    group_id = group.get("id")
    group_name = group.get("name")

    if group_role_lookup is not None:
        if isinstance(group_id, str) and group_id.strip():
            mapped_roles = group_role_lookup["by_group_id"].get(group_id.strip())
            if mapped_roles is not None:
                return mapped_roles

        group_name_key = _role_lookup_key(group_name if isinstance(group_name, str) else None)
        if group_name_key:
            mapped_roles = group_role_lookup["by_group_name"].get(group_name_key)
            if mapped_roles is not None:
                return mapped_roles

    effective_group = (
        get_organization_group_by_id(
            organization_id,
            group_id.strip(),
            admin_token=admin_token,
        )
        if organization_id and isinstance(group_id, str) and group_id.strip()
        else None
    ) or group
    return _mapped_roles_from_group(effective_group)


def _normalized_member_roles(
    organization_id: str,
    member_id: str,
    *,
    group_role_lookup: dict[str, dict[str, list[str]]] | None = None,
    admin_token: str | None = None,
) -> list[str]:
    effective_group_role_lookup = group_role_lookup or _organization_group_role_lookup(
        organization_id,
        admin_token=admin_token,
    )
    roles: set[str] = set()
    for group in get_organization_member_groups(
        organization_id,
        member_id,
        admin_token=admin_token,
    ):
        if not isinstance(group, Mapping):
            continue
        roles.update(
            _roles_for_group(
                group,
                organization_id=organization_id,
                group_role_lookup=effective_group_role_lookup,
                admin_token=admin_token,
            )
        )
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


def _serialize_group_member(member: Mapping[str, Any]) -> dict[str, Any]:
    serialized_member = _serialize_member(member, roles=[])
    serialized_member.pop("roles", None)
    return serialized_member


def _parallel_lookup_worker_count(item_count: int) -> int:
    return max(1, min(MAX_PARALLEL_KEYCLOAK_LOOKUPS, item_count))


def _organization_member_username_lookup(
    organization_id: str,
    usernames: list[str],
    *,
    admin_token: str | None = None,
) -> set[str]:
    normalized_usernames = list(
        {
            username.strip()
            for username in usernames
            if isinstance(username, str) and username.strip()
        }
    )
    if not normalized_usernames:
        return set()

    def load_membership(username: str) -> str | None:
        member = get_organization_member_by_username(
            organization_id,
            username,
            admin_token=admin_token,
        )
        if not isinstance(member, Mapping):
            return None
        member_username = member.get("username")
        if not isinstance(member_username, str) or not member_username.strip():
            return None
        return member_username.strip().casefold()

    if len(normalized_usernames) == 1:
        membership = load_membership(normalized_usernames[0])
        return {membership} if membership else set()

    existing_usernames: set[str] = set()
    with ThreadPoolExecutor(
        max_workers=_parallel_lookup_worker_count(len(normalized_usernames))
    ) as executor:
        future_by_username = {
            executor.submit(load_membership, username): username
            for username in normalized_usernames
        }
        for future in as_completed(future_by_username):
            membership = future.result()
            if membership:
                existing_usernames.add(membership)

    return existing_usernames


def _organization_group_members_lookup(
    organization_id: str,
    groups: list[dict[str, Any]],
    *,
    admin_token: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    group_ids = [
        group_id.strip()
        for group in groups
        for group_id in [group.get("id")]
        if isinstance(group_id, str) and group_id.strip()
    ]
    if not group_ids:
        return {}

    def load_group_members(group_id: str) -> list[dict[str, Any]]:
        members = [
            _serialize_group_member(member)
            for member in list_organization_group_members(
                organization_id,
                group_id,
                admin_token=admin_token,
            )
            if isinstance(member, Mapping)
        ]
        members.sort(key=lambda item: str(item.get("username") or ""))
        return members

    if len(group_ids) == 1:
        group_id = group_ids[0]
        return {group_id: load_group_members(group_id)}

    members_by_group_id: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=_parallel_lookup_worker_count(len(group_ids))) as executor:
        future_by_group_id = {
            executor.submit(load_group_members, group_id): group_id for group_id in group_ids
        }
        for future in as_completed(future_by_group_id):
            group_id = future_by_group_id[future]
            members_by_group_id[group_id] = future.result()

    return members_by_group_id


def _tenant_member_roles_lookup(
    organization_id: str,
    members: list[dict[str, Any]],
    *,
    group_role_lookup: dict[str, dict[str, list[str]]] | None = None,
    admin_token: str | None = None,
) -> dict[str, list[str]]:
    member_ids = [
        member_id.strip()
        for member in members
        for member_id in [member.get("id")]
        if isinstance(member_id, str) and member_id.strip()
    ]
    if not member_ids:
        return {}

    def load_member_roles(member_id: str) -> list[str]:
        return _normalized_member_roles(
            organization_id,
            member_id,
            group_role_lookup=group_role_lookup,
            admin_token=admin_token,
        )

    if len(member_ids) == 1:
        member_id = member_ids[0]
        return {member_id: load_member_roles(member_id)}

    roles_by_member_id: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=_parallel_lookup_worker_count(len(member_ids))) as executor:
        future_by_member_id = {
            executor.submit(load_member_roles, member_id): member_id for member_id in member_ids
        }
        for future in as_completed(future_by_member_id):
            member_id = future_by_member_id[future]
            roles_by_member_id[member_id] = future.result()

    return roles_by_member_id


def _mapped_roles_for_group(
    group: Mapping[str, Any],
    *,
    organization_id: str | None = None,
    group_role_lookup: dict[str, dict[str, list[str]]] | None = None,
    admin_token: str | None = None,
) -> list[str]:
    return _roles_for_group(
        group,
        organization_id=organization_id,
        group_role_lookup=group_role_lookup,
        admin_token=admin_token,
    )


def _organization_group_name_for_role_name(role_name: str) -> str:
    candidates = organization_group_name_candidates_for_tenant_role(role_name)
    if not candidates:
        raise ApiError(
            error_code="invalid_role",
            message=f"Role '{role_name}' is not a supported tenant role.",
            status_code=400,
        )
    return candidates[0]


def _organization_group_names_for_role_name(role_name: str) -> tuple[str, ...]:
    candidates = organization_group_name_candidates_for_tenant_role(role_name)
    if not candidates:
        raise ApiError(
            error_code="invalid_role",
            message=f"Role '{role_name}' is not a supported tenant role.",
            status_code=400,
        )
    return candidates


def _normalize_group_name(group_name: str | None) -> str:
    return str(group_name or "").strip().strip("/")


def _normalize_new_group_name(group_name: str | None) -> str:
    return " ".join(str(group_name or "").strip().split())


def _validated_new_group_name(group_name: str | None) -> str:
    normalized_group_name = _normalize_new_group_name(group_name)
    if not normalized_group_name:
        raise ApiError(
            error_code="invalid_group",
            message="Group name is required.",
            status_code=400,
        )

    if len(normalized_group_name) > TENANT_GROUP_NAME_MAX_LENGTH:
        raise ApiError(
            error_code="invalid_group",
            message=(
                f"Group name must be {TENANT_GROUP_NAME_MAX_LENGTH} characters or fewer."
            ),
            status_code=400,
        )

    if not TENANT_GROUP_NAME_ALLOWED_PATTERN.fullmatch(normalized_group_name):
        raise ApiError(
            error_code="invalid_group",
            message=(
                "Group name can only contain letters, numbers, spaces, hyphens, "
                "and underscores, and must start and end with a letter or number."
            ),
            status_code=400,
        )

    return normalized_group_name


def _group_name_conflict_key(group_name: str | None) -> str:
    normalized_group_name = _normalize_new_group_name(_normalize_group_name(group_name))
    return normalized_group_name.casefold() if normalized_group_name else ""


def _organization_group_name_lookup(organization_id: str) -> dict[str, str]:
    group_name_lookup: dict[str, str] = {}
    for group in list_organization_groups(organization_id):
        group_name = _normalize_group_name(group.get("name"))
        if not group_name:
            continue
        group_name_lookup[group_name.casefold()] = group_name
    return group_name_lookup


def _validated_group_names(
    organization_id: str,
    group_names: list[str] | tuple[str, ...] | str | None,
) -> list[str]:
    if not group_names:
        return []

    if isinstance(group_names, str):
        raw_group_names: list[str] = [group_names]
    elif isinstance(group_names, (list, tuple)):
        raw_group_names = list(group_names)
    else:
        raise ApiError(
            error_code="invalid_group",
            message="Group names must be a string or a list of strings.",
            status_code=400,
        )

    available_group_names = _organization_group_name_lookup(organization_id)
    normalized_group_names: list[str] = []
    seen_group_names: set[str] = set()

    for group_name in raw_group_names:
        normalized_group_name = _normalize_group_name(group_name)
        if not normalized_group_name:
            continue
        canonical_group_name = available_group_names.get(normalized_group_name.casefold())
        if not canonical_group_name:
            raise ApiError(
                error_code="invalid_group",
                message=f"Group '{group_name}' does not exist in the tenant organization.",
                status_code=400,
            )
        if canonical_group_name.casefold() in seen_group_names:
            continue
        seen_group_names.add(canonical_group_name.casefold())
        normalized_group_names.append(canonical_group_name)

    return normalized_group_names


def _organization_group_or_error(organization_id: str, group_name: str) -> dict[str, Any]:
    validated_group_names = _validated_group_names(organization_id, [group_name])
    if not validated_group_names:
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{group_name}' does not exist in the tenant organization.",
            status_code=400,
        )

    canonical_group_name = validated_group_names[0]
    for group in list_organization_groups(organization_id):
        candidate_name = _normalize_group_name(group.get("name"))
        if candidate_name.casefold() == canonical_group_name.casefold():
            return group

    raise ApiError(
        error_code="invalid_group",
        message=f"Group '{canonical_group_name}' does not exist in the tenant organization.",
        status_code=400,
    )


def _serialize_group(
    organization_id: str,
    group: Mapping[str, Any],
    *,
    group_role_lookup: dict[str, dict[str, list[str]]] | None = None,
    members_by_group_id: dict[str, list[dict[str, Any]]] | None = None,
    admin_token: str | None = None,
) -> dict[str, Any] | None:
    group_id = group.get("id")
    group_name = group.get("name")
    if not isinstance(group_id, str) or not group_id.strip():
        return None
    if not isinstance(group_name, str) or not group_name.strip():
        return None

    normalized_group_id = group_id.strip()
    members = (
        members_by_group_id.get(normalized_group_id)
        if members_by_group_id is not None
        else None
    )
    if members is None:
        members = [
            _serialize_group_member(member)
            for member in list_organization_group_members(
                organization_id,
                normalized_group_id,
                admin_token=admin_token,
            )
            if isinstance(member, Mapping)
        ]
        members.sort(key=lambda item: str(item.get("username") or ""))

    return {
        "id": normalized_group_id,
        "name": group_name.strip(),
        "path": group.get("path"),
        "mapped_roles": _mapped_roles_for_group(
            group,
            organization_id=organization_id,
            group_role_lookup=group_role_lookup,
            admin_token=admin_token,
        ),
        "member_count": len(members),
        "members": members,
    }


def _tenant_group_matches_search(group: Mapping[str, Any], search: str) -> bool:
    normalized_search = str(search or "").strip().lower()
    if not normalized_search:
        return True

    candidates: list[str] = []
    for value in (
        group.get("name"),
        group.get("path"),
        *(group.get("mapped_roles") or []),
    ):
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip().lower())

    for member in group.get("members") or []:
        if not isinstance(member, Mapping):
            continue
        for value in (
            member.get("username"),
            member.get("display_name"),
            member.get("email"),
        ):
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip().lower())

    return any(normalized_search in candidate for candidate in candidates)


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


def _sync_local_role_assignments(user: Any, tenant_id: str, roles: list[str]) -> None:
    added_group_ids: set[int] = set()
    removed_group_ids: set[int] = set()
    desired_roles = {role_name for role_name in roles if role_name in VALID_TENANT_ROLE_NAMES}

    for role_name in sorted(VALID_TENANT_ROLE_NAMES):
        group = _tenant_role_group(role_name, tenant_id)
        if role_name in desired_roles:
            assignment_created = _ensure_local_assignment(user, group, tenant_id)
            if assignment_created:
                added_group_ids.add(group.id)
            continue

        assignment_deleted = _delete_local_assignment(user, group, tenant_id)
        if assignment_deleted:
            removed_group_ids.add(group.id)

    if not added_group_ids and not removed_group_ids:
        return

    UserService.update_human_task_assignments_for_user(
        user,
        new_group_ids=added_group_ids,
        old_group_ids=removed_group_ids,
    )


def _sync_local_member_from_keycloak_member(
    tenant: Any,
    organization_id: str,
    member: Mapping[str, Any],
    *,
    group_role_lookup: dict[str, dict[str, list[str]]] | None = None,
) -> tuple[Any, list[str]]:
    username = str(member.get("username") or "").strip()
    member_id = str(member.get("id") or "").strip()
    if not username:
        raise ApiError(
            error_code="tenant_member_not_found",
            message="Tenant member does not have a valid username.",
            status_code=400,
        )
    if not member_id:
        raise ApiError(
            error_code="tenant_member_not_found",
            message=f"User '{username}' does not have a valid Keycloak membership id.",
            status_code=400,
        )

    local_user = _upsert_local_member_or_error(member, username)
    roles = _normalized_member_roles(
        organization_id,
        member_id,
        group_role_lookup=group_role_lookup,
    )
    _sync_local_role_assignments(local_user, tenant.id, roles)
    _ensure_tenant_yaml_permissions_and_everybody_membership(local_user, tenant.id)
    return local_user, roles


def _sync_local_members_for_group(
    tenant: Any,
    organization_id: str,
    group: Mapping[str, Any],
    *,
    group_role_lookup: dict[str, dict[str, list[str]]] | None = None,
) -> None:
    group_id = group.get("id")
    if not isinstance(group_id, str) or not group_id.strip():
        return

    effective_group_role_lookup = group_role_lookup or _organization_group_role_lookup(organization_id)
    for member in list_organization_group_members(organization_id, group_id.strip()):
        if not isinstance(member, Mapping):
            continue
        _sync_local_member_from_keycloak_member(
            tenant,
            organization_id,
            member,
            group_role_lookup=effective_group_role_lookup,
        )


def _delete_local_assignment(user: Any, group: Any, tenant_id: str) -> bool:
    assignment = _local_assignment_query(user, group, tenant_id).first()
    if assignment is None:
        return False
    db.session.delete(assignment)
    db.session.commit()
    return True


def _tenant_member_or_error(organization_id: str, tenant_slug: str, username: str) -> dict[str, Any]:
    member = get_organization_member_by_username(organization_id, username)
    if isinstance(member, dict):
        return member
    raise ApiError(
        error_code="tenant_member_not_found",
        message=f"User '{username}' is not a member of organization '{tenant_slug}'.",
        status_code=404,
    )


def _tenant_member_id_or_error(member: Mapping[str, Any], username: str) -> str:
    member_id = member.get("id")
    if isinstance(member_id, str) and member_id.strip():
        return member_id.strip()
    raise ApiError(
        error_code="tenant_member_not_found",
        message=f"User '{username}' does not have a valid Keycloak membership id.",
        status_code=400,
    )


def _upsert_local_member_or_error(member: Mapping[str, Any], username: str) -> Any:
    local_user = upsert_local_shared_realm_member(member)
    if local_user is not None:
        return local_user
    raise ApiError(
        error_code="local_user_sync_failed",
        message=(
            f"User '{username}' was updated in Keycloak, but the local M8Flow user row "
            "could not be created or refreshed."
        ),
        status_code=409,
    )


def list_tenant_members_with_roles(
    tenant_id: str,
    *,
    search: str | None = None,
    max_results: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return organization members for one tenant with their org-local tenant roles."""
    admin_token = get_master_admin_token()
    _tenant, _organization, organization_id = _organization_for_tenant(
        tenant_id,
        admin_token=admin_token,
    )
    members = search_organization_members(
        organization_id,
        search or "",
        exact=False,
        max_results=max_results,
        first_result=offset,
        admin_token=admin_token,
    )
    if not members:
        return []

    organization_groups = list_organization_groups(
        organization_id,
        admin_token=admin_token,
        brief_representation=False,
    )
    group_role_lookup = _organization_group_role_lookup(
        organization_id,
        admin_token=admin_token,
        groups=organization_groups,
    )
    member_roles_lookup = _tenant_member_roles_lookup(
        organization_id,
        members,
        group_role_lookup=group_role_lookup,
        admin_token=admin_token,
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
                roles=member_roles_lookup.get(member_id.strip(), []),
            )
        )

    serialized_members.sort(key=lambda item: str(item.get("username") or ""))
    return serialized_members


def list_available_tenant_users(
    tenant_id: str,
    *,
    search: str | None = None,
    max_results: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return existing realm users that are not yet members of the selected tenant."""
    admin_token = get_master_admin_token()
    _tenant, _organization, organization_id = _organization_for_tenant(
        tenant_id,
        admin_token=admin_token,
    )
    normalized_search = str(search or "").strip()
    normalized_offset = max(0, offset)
    normalized_limit = max(1, max_results)
    batch_size = max(25, normalized_limit * 2)

    available_users: list[dict[str, Any]] = []
    available_users_skipped = 0
    realm_offset = 0

    while len(available_users) < normalized_limit:
        realm_users = search_realm_users(
            shared_realm_name(),
            normalized_search,
            exact=False,
            max_results=batch_size,
            first_result=realm_offset,
            admin_token=admin_token,
        )
        if not realm_users:
            break

        existing_usernames = _organization_member_username_lookup(
            organization_id,
            [
                username
                for user in realm_users
                for username in [user.get("username")]
                if isinstance(username, str)
            ],
            admin_token=admin_token,
        )

        for user in realm_users:
            username = user.get("username")
            if not isinstance(username, str) or not username.strip():
                continue
            if username.strip().casefold() in existing_usernames:
                continue
            if available_users_skipped < normalized_offset:
                available_users_skipped += 1
                continue
            available_users.append(_serialize_group_member(user))
            if len(available_users) >= normalized_limit:
                break

        realm_offset += len(realm_users)
        if len(realm_users) < batch_size:
            break

    return available_users


def list_tenant_groups_with_members(
    tenant_id: str,
    *,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Return Keycloak organization groups for one tenant with mapped tenant roles and members."""
    admin_token = get_master_admin_token()
    _tenant, _organization, organization_id = _organization_for_tenant(
        tenant_id,
        admin_token=admin_token,
    )
    organization_groups = list_organization_groups(
        organization_id,
        admin_token=admin_token,
        brief_representation=False,
    )
    group_role_lookup = _organization_group_role_lookup(
        organization_id,
        admin_token=admin_token,
        groups=organization_groups,
    )
    members_by_group_id = _organization_group_members_lookup(
        organization_id,
        organization_groups,
        admin_token=admin_token,
    )
    serialized_groups: list[dict[str, Any]] = []

    for group in organization_groups:
        serialized_group = _serialize_group(
            organization_id,
            group,
            group_role_lookup=group_role_lookup,
            members_by_group_id=members_by_group_id,
            admin_token=admin_token,
        )
        if serialized_group is None:
            continue
        if _tenant_group_matches_search(serialized_group, search or ""):
            serialized_groups.append(serialized_group)

    serialized_groups.sort(key=lambda item: str(item.get("name") or ""))
    return serialized_groups


def create_tenant_group(tenant_id: str, group_name: str) -> dict[str, Any]:
    """Create one Keycloak organization group in one tenant and return the serialized group."""
    normalized_group_name = _validated_new_group_name(group_name)

    _tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    existing_group_names = _organization_group_name_lookup(organization_id)
    existing_group_name_keys = {
        _group_name_conflict_key(existing_group_name): existing_group_name
        for existing_group_name in existing_group_names.values()
    }
    if _group_name_conflict_key(normalized_group_name) in existing_group_name_keys:
        raise ApiError(
            error_code="group_exists",
            message=f"Group '{normalized_group_name}' already exists in the tenant organization.",
            status_code=409,
        )

    created_group = create_organization_group(organization_id, normalized_group_name)
    serialized_group = _serialize_group(organization_id, created_group)
    if serialized_group is None:
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{normalized_group_name}' could not be loaded after creation.",
            status_code=500,
        )
    return serialized_group


def add_tenant_member(
    tenant_id: str,
    *,
    username: str,
    group_names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Add one existing Keycloak user to one tenant organization and optionally assign organization groups."""
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ApiError(
            error_code="invalid_member",
            message="Username is required.",
            status_code=400,
        )

    tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    validated_group_names = _validated_group_names(organization_id, group_names)

    member = get_organization_member_by_username(organization_id, normalized_username)
    if not isinstance(member, dict):
        realm_name = shared_realm_name()
        realm_user = get_realm_user_by_username(realm_name, normalized_username)
        if not isinstance(realm_user, dict):
            raise ApiError(
                error_code="tenant_member_not_found",
                message=(
                    f"Existing user '{normalized_username}' could not be found in Keycloak."
                ),
                status_code=404,
            )

        user_id = realm_user.get("id")

        if not isinstance(user_id, str) or not user_id.strip():
            raise ApiError(
                error_code="invalid_member",
                message=f"User '{normalized_username}' does not have a valid Keycloak user id.",
                status_code=400,
            )

        add_organization_member(organization_id, user_id.strip())
        member = _tenant_member_or_error(organization_id, tenant.slug, normalized_username)

    member_id = _tenant_member_id_or_error(member, normalized_username)
    for group_name in validated_group_names:
        add_organization_group_member(organization_id, group_name, member_id)

    _local_user, roles = _sync_local_member_from_keycloak_member(
        tenant,
        organization_id,
        member,
    )
    return _serialize_member(member, roles=roles)


def add_tenant_group_member(tenant_id: str, username: str, group_name: str) -> dict[str, Any]:
    """Assign one tenant member to one existing organization group and mirror mapped roles locally."""
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ApiError(
            error_code="invalid_member",
            message="Username is required.",
            status_code=400,
        )

    tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    validated_group_names = _validated_group_names(organization_id, [group_name])
    member = _tenant_member_or_error(organization_id, tenant.slug, normalized_username)
    member_id = _tenant_member_id_or_error(member, normalized_username)

    add_organization_group_member(organization_id, validated_group_names[0], member_id)

    _local_user, roles = _sync_local_member_from_keycloak_member(
        tenant,
        organization_id,
        member,
    )
    return _serialize_member(member, roles=roles)


def remove_tenant_group_member(tenant_id: str, username: str, group_name: str) -> dict[str, Any]:
    """Remove one tenant member from one existing organization group and mirror mapped roles locally."""
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ApiError(
            error_code="invalid_member",
            message="Username is required.",
            status_code=400,
        )

    tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    validated_group_names = _validated_group_names(organization_id, [group_name])
    member = _tenant_member_or_error(organization_id, tenant.slug, normalized_username)
    member_id = _tenant_member_id_or_error(member, normalized_username)

    remove_organization_group_member(organization_id, validated_group_names[0], member_id)

    _local_user, roles = _sync_local_member_from_keycloak_member(
        tenant,
        organization_id,
        member,
    )
    return _serialize_member(member, roles=roles)


def assign_tenant_group_role(tenant_id: str, group_name: str, role_name: str) -> dict[str, Any]:
    """Grant one tenant-scoped role to one Keycloak organization group and mirror the result locally."""
    normalized_role_name = _normalize_role_name(role_name)
    tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    group = _organization_group_or_error(organization_id, group_name)
    group_id = group.get("id")
    if not isinstance(group_id, str) or not group_id.strip():
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{group_name}' does not have a valid Keycloak group id.",
            status_code=400,
        )

    updated_group = set_organization_group_role_names(
        organization_id,
        group_id.strip(),
        sorted(
            {
                *_mapped_roles_for_group(group, organization_id=organization_id),
                normalized_role_name,
            }
        ),
    )

    group_role_lookup = _organization_group_role_lookup(organization_id)
    _sync_local_members_for_group(
        tenant,
        organization_id,
        updated_group if isinstance(updated_group, Mapping) else group,
        group_role_lookup=group_role_lookup,
    )
    serialized_group = _serialize_group(
        organization_id,
        updated_group if isinstance(updated_group, Mapping) else group,
        group_role_lookup=group_role_lookup,
    )
    if serialized_group is None:
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{group_name}' could not be serialized after role assignment.",
            status_code=500,
        )
    return serialized_group


def remove_tenant_group_role(tenant_id: str, group_name: str, role_name: str) -> dict[str, Any]:
    """Remove one tenant-scoped role from one Keycloak organization group and mirror the result locally."""
    normalized_role_name = _normalize_role_name(role_name)
    tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    group = _organization_group_or_error(organization_id, group_name)
    group_id = group.get("id")
    if not isinstance(group_id, str) or not group_id.strip():
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{group_name}' does not have a valid Keycloak group id.",
            status_code=400,
        )

    updated_group = set_organization_group_role_names(
        organization_id,
        group_id.strip(),
        [
            mapped_role_name
            for mapped_role_name in _mapped_roles_for_group(group, organization_id=organization_id)
            if mapped_role_name != normalized_role_name
        ],
    )

    group_role_lookup = _organization_group_role_lookup(organization_id)
    _sync_local_members_for_group(
        tenant,
        organization_id,
        updated_group if isinstance(updated_group, Mapping) else group,
        group_role_lookup=group_role_lookup,
    )
    serialized_group = _serialize_group(
        organization_id,
        updated_group if isinstance(updated_group, Mapping) else group,
        group_role_lookup=group_role_lookup,
    )
    if serialized_group is None:
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{group_name}' could not be serialized after role removal.",
            status_code=500,
        )
    return serialized_group


def assign_tenant_role(tenant_id: str, username: str, role_name: str) -> dict[str, Any]:
    """Assign one tenant-scoped role to one organization member and mirror it locally."""
    normalized_role_name = _normalize_role_name(role_name)
    tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    member = _tenant_member_or_error(organization_id, tenant.slug, username)
    member_id = _tenant_member_id_or_error(member, username)

    add_organization_group_member(
        organization_id,
        _organization_group_name_for_role_name(normalized_role_name),
        member_id,
    )

    _local_user, updated_roles = _sync_local_member_from_keycloak_member(
        tenant,
        organization_id,
        member,
    )
    return _serialize_member(
        member,
        roles=updated_roles,
    )


def remove_tenant_role(tenant_id: str, username: str, role_name: str) -> dict[str, Any]:
    """Remove one tenant-scoped role from one organization member and mirror it locally."""
    normalized_role_name = _normalize_role_name(role_name)
    tenant, _organization, organization_id = _organization_for_tenant(tenant_id)
    member = _tenant_member_or_error(organization_id, tenant.slug, username)
    member_id = _tenant_member_id_or_error(member, username)

    for organization_group_name in _organization_group_names_for_role_name(normalized_role_name):
        remove_organization_group_member(
            organization_id,
            organization_group_name,
            member_id,
        )

    _local_user, updated_roles = _sync_local_member_from_keycloak_member(
        tenant,
        organization_id,
        member,
    )
    return _serialize_member(
        member,
        roles=updated_roles,
    )
