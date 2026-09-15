from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext as _permission_scope_tenant
from typing import Any

from m8flow_backend.integrations.auth import get_auth_provider
from m8flow_backend.integrations.auth.base.errors import TenantNotFound, UserNotFound
from m8flow_backend.integrations.auth.base.models import Group, TenantRef, User
from m8flow_backend.integrations.auth.base.roles import VALID_TENANT_ROLE_NAMES
from m8flow_backend.auth.identity_helpers import (
    member_mapping_from_user,
    qualified_config_group_identifier,
    qualify_group_identifier,
    upsert_local_shared_realm_member,
)
from m8flow_backend.services.tenant_service import TenantService
from m8flow_backend.errors import ApiError
from m8flow_backend.db import db
from m8flow_bpmn_core.models.user_group_assignment import UserGroupAssignmentModel
from m8flow_backend import identity

logger = logging.getLogger(__name__)

TENANT_GROUP_NAME_MAX_LENGTH = 64
TENANT_GROUP_NAME_ALLOWED_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9])?$")
MAX_PARALLEL_KEYCLOAK_LOOKUPS = 8


def _directory_admin():
    return get_auth_provider().directory_admin


def _group_for(organization_id: str, group_name: str) -> Group:
    return Group(identifier=str(group_name).strip(), tenant_ref=TenantRef(id=organization_id))


def _normalize_role_name(role_name: str) -> str:
    normalized_role_name = str(role_name or "").strip()
    if normalized_role_name not in VALID_TENANT_ROLE_NAMES:
        raise ApiError(
            error_code="invalid_role",
            message=f"Role '{role_name}' is not a supported tenant role.",
            status_code=400,
        )
    return normalized_role_name


def _organization_for_tenant(tenant_id: str) -> tuple[Any, str]:
    """Resolve a local tenant to its Keycloak organization id.

    Drained onto the capability surface (auth-provider-seam wayfinder map,
    ticket 15): ``get_tenant`` already does the id-then-alias fallback this
    used to do by hand (``tenants.resolve_tenant_ref``, confirmed by reading
    it), so this is now a single capability call instead of two raw ones.
    """
    tenant = TenantService.get_tenant_by_id(tenant_id)
    tenant_identifier = tenant.id.strip() if isinstance(tenant.id, str) and tenant.id.strip() else None
    tenant_alias = tenant.slug.strip() if isinstance(tenant.slug, str) and tenant.slug.strip() else None
    try:
        organization = _directory_admin().get_tenant(TenantRef(id=tenant_identifier, alias=tenant_alias))
    except TenantNotFound:
        raise ApiError(
            error_code="organization_not_found",
            message=(
                f"Organization for tenant '{tenant_identifier or tenant_id}'"
                f"{f' (alias: {tenant.slug})' if getattr(tenant, 'slug', None) else ''}"
                " could not be found in Keycloak."
            ),
            status_code=404,
        ) from None

    organization_id = organization.ref.id
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
    return tenant, organization_id.strip()


def _normalize_group_name(group_name: str | None) -> str:
    return str(group_name or "").strip().strip("/")


def _role_lookup_key(value: str | None) -> str:
    normalized_value = _normalize_group_name(value)
    return normalized_value.casefold() if normalized_value else ""


def _organization_group_role_lookup(tenant_ref: TenantRef) -> dict[str, list[str]]:
    """Every group's mapped roles, keyed by normalized group name.

    Drained (ticket 15, §2): the neutral ``Group`` model carries no
    Keycloak-internal id, only ``identifier``/``path``, so the former
    ``by_group_id``/``by_group_name`` dual lookup collapses to name-keyed
    only. This does one ``roles_for_group`` Admin API call per group instead
    of the old single bulk fetch -- a deliberate, accepted tradeoff (tenant
    group counts are small, and the cached admin token from ticket 08
    removes the expensive part of a repeated call).
    """
    roles_by_name: dict[str, list[str]] = {}
    for group in _directory_admin().list_groups(tenant_ref):
        roles_by_name[_role_lookup_key(group.identifier)] = _directory_admin().roles_for_group(group)
    return roles_by_name


def _roles_for_group(
    group: Group,
    *,
    group_role_lookup: dict[str, list[str]] | None = None,
) -> list[str]:
    if group_role_lookup is not None:
        mapped_roles = group_role_lookup.get(_role_lookup_key(group.identifier))
        if mapped_roles is not None:
            return mapped_roles
    return _directory_admin().roles_for_group(group)


def _serialize_member_group(group: Group) -> dict[str, Any] | None:
    if not group.identifier:
        return None
    # "id" repurposed to hold the group's name (ticket 15, §4): the neutral
    # Group model carries no vendor-specific id, and this was verified safe
    # against the m8flow-designer/m8flow-frontend consumers of this shape --
    # no code depends on it being a genuine Keycloak UUID.
    return {"id": group.identifier, "name": group.identifier}


def _normalized_member_access(
    username: str,
    tenant_ref: TenantRef,
    *,
    group_role_lookup: dict[str, list[str]] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    effective_group_role_lookup = group_role_lookup or _organization_group_role_lookup(tenant_ref)
    roles: set[str] = set()
    groups: list[dict[str, Any]] = []
    seen_group_names: set[str] = set()
    for group in _directory_admin().list_member_groups(username=username, tenant_ref=tenant_ref):
        serialized_group = _serialize_member_group(group)
        if serialized_group is not None and serialized_group["id"] not in seen_group_names:
            seen_group_names.add(serialized_group["id"])
            groups.append(serialized_group)
        roles.update(_roles_for_group(group, group_role_lookup=effective_group_role_lookup))
    groups.sort(key=lambda item: str(item.get("name") or ""))
    return sorted(roles), groups


def _normalized_member_roles(
    username: str,
    tenant_ref: TenantRef,
    *,
    group_role_lookup: dict[str, list[str]] | None = None,
) -> list[str]:
    roles, _groups = _normalized_member_access(username, tenant_ref, group_role_lookup=group_role_lookup)
    return roles


def _serialize_member(
    member: User,
    *,
    roles: list[str],
    groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": member.username,
        "username": member.username,
        "email": member.email,
        "display_name": member.display_name,
        "roles": roles,
        "groups": groups or [],
    }


def _serialize_group_member(member: User) -> dict[str, Any]:
    return {
        "id": member.username,
        "username": member.username,
        "email": member.email,
        "display_name": member.display_name,
    }


def _parallel_lookup_worker_count(item_count: int) -> int:
    return max(1, min(MAX_PARALLEL_KEYCLOAK_LOOKUPS, item_count))


def _organization_member_username_lookup(
    tenant_ref: TenantRef,
    usernames: list[str],
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
        try:
            member = _directory_admin().get_member(username=username, tenant_ref=tenant_ref)
        except UserNotFound:
            return None
        if not member.username:
            return None
        return member.username.strip().casefold()

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
    groups: list[Group],
) -> dict[str, list[dict[str, Any]]]:
    group_names = [group.identifier for group in groups if group.identifier]
    if not group_names:
        return {}
    groups_by_name = {group.identifier: group for group in groups if group.identifier}

    def load_group_members(group_name: str) -> list[dict[str, Any]]:
        members = [_serialize_group_member(member) for member in _directory_admin().list_group_members(groups_by_name[group_name])]
        members.sort(key=lambda item: str(item.get("username") or ""))
        return members

    if len(group_names) == 1:
        group_name = group_names[0]
        return {group_name: load_group_members(group_name)}

    members_by_group_name: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=_parallel_lookup_worker_count(len(group_names))) as executor:
        future_by_group_name = {
            executor.submit(load_group_members, group_name): group_name for group_name in group_names
        }
        for future in as_completed(future_by_group_name):
            group_name = future_by_group_name[future]
            members_by_group_name[group_name] = future.result()

    return members_by_group_name


def _tenant_member_roles_lookup(
    tenant_ref: TenantRef,
    members: list[User],
    *,
    group_role_lookup: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    # Keyed by member.subject (the Keycloak membership id every caller here
    # indexes by) but threaded via member.username -- list_member_groups
    # needs a username, not the id (ticket 15, §3).
    member_pairs = [
        (member.subject, member.username)
        for member in members
        if member.subject and member.username
    ]
    if not member_pairs:
        return {}

    def load_member_roles(pair: tuple[str, str]) -> list[str]:
        _member_id, username = pair
        return _normalized_member_roles(username, tenant_ref, group_role_lookup=group_role_lookup)

    if len(member_pairs) == 1:
        member_id, username = member_pairs[0]
        return {member_id: load_member_roles((member_id, username))}

    roles_by_member_id: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=_parallel_lookup_worker_count(len(member_pairs))) as executor:
        future_by_pair = {
            executor.submit(load_member_roles, pair): pair for pair in member_pairs
        }
        for future in as_completed(future_by_pair):
            member_id, _username = future_by_pair[future]
            roles_by_member_id[member_id] = future.result()

    return roles_by_member_id


def _tenant_member_access_lookup(
    tenant_ref: TenantRef,
    members: list[User],
    *,
    group_role_lookup: dict[str, list[str]] | None = None,
) -> dict[str, dict[str, Any]]:
    member_pairs = [
        (member.subject, member.username)
        for member in members
        if member.subject and member.username
    ]
    if not member_pairs:
        return {}

    def load_member_access(pair: tuple[str, str]) -> dict[str, Any]:
        _member_id, username = pair
        roles, groups = _normalized_member_access(username, tenant_ref, group_role_lookup=group_role_lookup)
        return {"roles": roles, "groups": groups}

    if len(member_pairs) == 1:
        member_id, username = member_pairs[0]
        return {member_id: load_member_access((member_id, username))}

    access_by_member_id: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=_parallel_lookup_worker_count(len(member_pairs))) as executor:
        future_by_pair = {
            executor.submit(load_member_access, pair): pair for pair in member_pairs
        }
        for future in as_completed(future_by_pair):
            member_id, _username = future_by_pair[future]
            access_by_member_id[member_id] = future.result()

    return access_by_member_id


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


def _organization_group_name_lookup(tenant_ref: TenantRef) -> dict[str, str]:
    group_name_lookup: dict[str, str] = {}
    for group in _directory_admin().list_groups(tenant_ref):
        group_name = _normalize_group_name(group.identifier)
        if not group_name:
            continue
        group_name_lookup[group_name.casefold()] = group_name
    return group_name_lookup


def _validated_group_names(
    tenant_ref: TenantRef,
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

    available_group_names = _organization_group_name_lookup(tenant_ref)
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


def _organization_group_or_error(tenant_ref: TenantRef, group_name: str) -> Group:
    validated_group_names = _validated_group_names(tenant_ref, [group_name])
    if not validated_group_names:
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{group_name}' does not exist in the tenant organization.",
            status_code=400,
        )

    canonical_group_name = validated_group_names[0]
    for group in _directory_admin().list_groups(tenant_ref):
        if _normalize_group_name(group.identifier).casefold() == canonical_group_name.casefold():
            return group

    raise ApiError(
        error_code="invalid_group",
        message=f"Group '{canonical_group_name}' does not exist in the tenant organization.",
        status_code=400,
    )


def _serialize_group(
    tenant_ref: TenantRef,
    group: Group,
    *,
    group_role_lookup: dict[str, list[str]] | None = None,
    members_by_group_name: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any] | None:
    if not group.identifier:
        return None

    members = (
        members_by_group_name.get(group.identifier)
        if members_by_group_name is not None
        else None
    )
    if members is None:
        members = [_serialize_group_member(member) for member in _directory_admin().list_group_members(group)]
        members.sort(key=lambda item: str(item.get("username") or ""))

    return {
        # "id" repurposed to hold the group's name (ticket 15, §4) -- see
        # _serialize_member_group's docstring for the same repurposing and
        # the frontend verification behind it.
        "id": group.identifier,
        "name": group.identifier,
        "path": group.path,
        "mapped_roles": _roles_for_group(group, group_role_lookup=group_role_lookup),
        "member_count": len(members),
        "members": members,
    }


def _tenant_group_matches_search(
    group: Group,
    search: str,
    *,
    mapped_roles: list[str] | None = None,
) -> bool:
    normalized_search = str(search or "").strip().lower()
    if not normalized_search:
        return True

    candidates: list[str] = []
    for value in (group.identifier, group.path, *(mapped_roles or [])):
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip().lower())

    return any(normalized_search in candidate for candidate in candidates)


def _tenant_role_group(role_name: str, tenant_id: str) -> Any:
    group_identifier = qualify_group_identifier(role_name, tenant_id=tenant_id)
    return identity.ensure_group(group_identifier, source_is_open_id=True)


def _local_assignment_query(user: Any, group: Any, tenant_id: str):
    query = db.session.query(UserGroupAssignmentModel).filter_by(user_id=user.id, group_id=group.id)
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
    SpiffWorkflow grants to every signed-in user. Tenant-qualification comes solely
    from the explicit `tenant_id` argument passed to `identity.import_yaml()` below;
    `_permission_scope_tenant` is `contextlib.nullcontext` (a no-op) and provides no
    scoping of its own.
    """
    with _permission_scope_tenant():
        identity.import_yaml(tenant_id=tenant_id)


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


def _sync_local_member_from_keycloak_member(
    tenant: Any,
    tenant_ref: TenantRef,
    member: User,
    *,
    group_role_lookup: dict[str, list[str]] | None = None,
) -> tuple[Any, list[str]]:
    username = str(member.username or "").strip()
    if not username:
        raise ApiError(
            error_code="tenant_member_not_found",
            message="Tenant member does not have a valid username.",
            status_code=400,
        )

    local_user = _upsert_local_member_or_error(member, username)
    roles = _normalized_member_roles(username, tenant_ref, group_role_lookup=group_role_lookup)
    _sync_local_role_assignments(local_user, tenant.id, roles)
    _ensure_tenant_yaml_permissions_and_everybody_membership(local_user, tenant.id)
    return local_user, roles


def _sync_local_members_for_group(
    tenant: Any,
    tenant_ref: TenantRef,
    group: Group,
    *,
    group_role_lookup: dict[str, list[str]] | None = None,
) -> None:
    if not group.identifier:
        return

    effective_group_role_lookup = group_role_lookup or _organization_group_role_lookup(tenant_ref)
    for member in _directory_admin().list_group_members(group):
        _sync_local_member_from_keycloak_member(
            tenant,
            tenant_ref,
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


def _clear_local_tenant_assignments(user: Any, tenant_id: str) -> None:
    removed_group_ids: set[int] = set()

    if hasattr(UserGroupAssignmentModel, "m8f_tenant_id"):
        assignments = (
            db.session.query(UserGroupAssignmentModel).filter_by(user_id=user.id)
            .filter_by(m8f_tenant_id=tenant_id)
            .all()
        )
        if not assignments:
            return

        for assignment in assignments:
            group_id = getattr(assignment, "group_id", None)
            if isinstance(group_id, int):
                removed_group_ids.add(group_id)
            db.session.delete(assignment)
        db.session.commit()
    else:
        group_identifiers = {
            qualify_group_identifier(role_name, tenant_id=tenant_id)
            for role_name in VALID_TENANT_ROLE_NAMES
        }
        default_group_identifier = qualified_config_group_identifier(
            "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
            tenant_id=tenant_id,
        )
        if default_group_identifier:
            group_identifiers.add(default_group_identifier)

        for group_identifier in sorted(group_identifiers):
            group = identity.ensure_group(group_identifier, source_is_open_id=True)
            assignment_deleted = _delete_local_assignment(user, group, tenant_id)
            if assignment_deleted:
                removed_group_ids.add(group.id)

    if removed_group_ids:
        return


def _tenant_member_or_error(tenant_ref: TenantRef, tenant_slug: str, username: str) -> User:
    try:
        return _directory_admin().get_member(username=username, tenant_ref=tenant_ref)
    except UserNotFound:
        raise ApiError(
            error_code="tenant_member_not_found",
            message=f"User '{username}' is not a member of organization '{tenant_slug}'.",
            status_code=404,
        ) from None


def _upsert_local_member_or_error(member: User, username: str) -> Any:
    local_user = upsert_local_shared_realm_member(member_mapping_from_user(member))
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
    _tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    members = _directory_admin().list_members(
        tenant_ref=tenant_ref,
        query=search or "",
        limit=max_results,
        offset=offset,
    )
    if not members:
        return []

    group_role_lookup = _organization_group_role_lookup(tenant_ref)
    member_access_lookup = _tenant_member_access_lookup(
        tenant_ref,
        members,
        group_role_lookup=group_role_lookup,
    )

    serialized_members: list[dict[str, Any]] = []
    for member in members:
        if not member.subject or not member.username:
            continue
        member_access = member_access_lookup.get(
            member.subject,
            {"roles": [], "groups": []},
        )
        serialized_members.append(
            _serialize_member(
                member,
                roles=member_access.get("roles", []),
                groups=member_access.get("groups", []),
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
    _tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    normalized_search = str(search or "").strip()
    normalized_offset = max(0, offset)
    normalized_limit = max(1, max_results)
    batch_size = max(25, normalized_limit * 2)
    issuer = get_auth_provider().default_issuer()

    available_users: list[dict[str, Any]] = []
    available_users_skipped = 0
    realm_offset = 0

    while len(available_users) < normalized_limit:
        realm_users = get_auth_provider().search_users(
            query=normalized_search,
            issuer=issuer,
            limit=batch_size,
            offset=realm_offset,
        )
        if not realm_users:
            break

        existing_usernames = _organization_member_username_lookup(
            tenant_ref,
            [user.username for user in realm_users if user.username],
        )

        for user in realm_users:
            if not user.username or not user.username.strip():
                continue
            if user.username.strip().casefold() in existing_usernames:
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
    max_results: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return Keycloak organization groups for one tenant with mapped tenant roles and members."""
    _tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    organization_groups = _directory_admin().list_groups(tenant_ref)
    group_role_lookup = _organization_group_role_lookup(tenant_ref)
    matching_groups: list[Group] = []

    for group in organization_groups:
        mapped_roles = _roles_for_group(group, group_role_lookup=group_role_lookup)
        if _tenant_group_matches_search(group, search or "", mapped_roles=mapped_roles):
            matching_groups.append(group)

    matching_groups.sort(key=lambda item: item.identifier or "")
    paged_groups = matching_groups[offset : offset + max_results]
    members_by_group_name = _organization_group_members_lookup(paged_groups)
    serialized_groups: list[dict[str, Any]] = []

    for group in paged_groups:
        serialized_group = _serialize_group(
            tenant_ref,
            group,
            group_role_lookup=group_role_lookup,
            members_by_group_name=members_by_group_name,
        )
        if serialized_group is None:
            continue
        serialized_groups.append(serialized_group)

    return serialized_groups


def create_tenant_group(tenant_id: str, group_name: str) -> dict[str, Any]:
    """Create one Keycloak organization group in one tenant and return the serialized group."""
    normalized_group_name = _validated_new_group_name(group_name)

    _tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    existing_group_names = _organization_group_name_lookup(tenant_ref)
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

    created_group = _directory_admin().create_group(tenant_ref, identifier=normalized_group_name)
    serialized_group = _serialize_group(tenant_ref, created_group)
    if serialized_group is None:
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{normalized_group_name}' could not be loaded after creation.",
            status_code=500,
        )
    return serialized_group


def rename_tenant_group(tenant_id: str, group_name: str, new_group_name: str) -> dict[str, Any]:
    """Rename one Keycloak organization group in one tenant and preserve its granted roles."""
    normalized_group_name = _validated_new_group_name(new_group_name)
    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    group = _organization_group_or_error(tenant_ref, group_name)
    current_group_name = _normalize_group_name(group.identifier)

    existing_group_names = _organization_group_name_lookup(tenant_ref)
    existing_group_name_keys = {
        _group_name_conflict_key(existing_group_name): existing_group_name
        for existing_group_name in existing_group_names.values()
    }
    normalized_group_conflict_key = _group_name_conflict_key(normalized_group_name)
    current_group_conflict_key = _group_name_conflict_key(current_group_name)
    conflicting_group_name = existing_group_name_keys.get(normalized_group_conflict_key)
    if (
        conflicting_group_name
        and normalized_group_conflict_key != current_group_conflict_key
    ):
        raise ApiError(
            error_code="group_exists",
            message=f"Group '{normalized_group_name}' already exists in the tenant organization.",
            status_code=409,
        )

    if normalized_group_name == current_group_name:
        serialized_group = _serialize_group(tenant_ref, group)
        if serialized_group is None:
            raise ApiError(
                error_code="invalid_group",
                message=f"Group '{current_group_name or group_name}' could not be serialized.",
                status_code=500,
            )
        return serialized_group

    renamed_group = _directory_admin().rename_group(
        group,
        identifier=normalized_group_name,
        roles=list(_roles_for_group(group)),
    )

    group_role_lookup = _organization_group_role_lookup(tenant_ref)
    _sync_local_members_for_group(
        tenant,
        tenant_ref,
        renamed_group,
        group_role_lookup=group_role_lookup,
    )
    serialized_group = _serialize_group(
        tenant_ref,
        renamed_group,
        group_role_lookup=group_role_lookup,
    )
    if serialized_group is None:
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{normalized_group_name}' could not be serialized after rename.",
            status_code=500,
        )
    return serialized_group


def add_tenant_member(
    tenant_id: str,
    *,
    username: str,
    group_names: list[str] | tuple[str, ...] | None = None,
    roles: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Add one existing Keycloak user to one tenant organization and optionally
    assign explicit organization groups and/or tenant-scoped roles.

    `group_names` and `roles` are independent, additive mechanisms: the
    former adds to specific, caller-named groups (the route's own API
    shape); the latter maps each neutral role name to its group via
    `SupportsRoleAdmin.assign_roles`, the same capability
    `assign_tenant_role` uses -- added so callers with roles in hand (e.g.
    `tenant_invitation_service.accept_invitation`) never need Keycloak's own
    role-to-group-name mapping table directly (auth-provider-seam wayfinder
    map, ticket 16)."""
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ApiError(
            error_code="invalid_member",
            message="Username is required.",
            status_code=400,
        )

    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    validated_group_names = _validated_group_names(tenant_ref, group_names)

    try:
        member = _directory_admin().get_member(username=normalized_username, tenant_ref=tenant_ref)
    except UserNotFound:
        try:
            get_auth_provider().get_user(username=normalized_username, issuer=get_auth_provider().default_issuer())
        except UserNotFound:
            raise ApiError(
                error_code="tenant_member_not_found",
                message=(
                    f"Existing user '{normalized_username}' could not be found in Keycloak."
                ),
                status_code=404,
            ) from None

        _directory_admin().add_member(username=normalized_username, tenant_ref=tenant_ref)
        member = _tenant_member_or_error(tenant_ref, tenant.slug, normalized_username)

    for group_name in validated_group_names:
        _directory_admin().add_group_member(
            _group_for(organization_id, group_name),
            username=normalized_username,
        )

    if roles:
        _directory_admin().assign_roles(
            username=normalized_username,
            tenant_ref=tenant_ref,
            roles=[_normalize_role_name(role_name) for role_name in roles],
        )

    _local_user, updated_roles = _sync_local_member_from_keycloak_member(
        tenant,
        tenant_ref,
        member,
    )
    return _serialize_member(member, roles=updated_roles)


def remove_tenant_member(tenant_id: str, username: str) -> str:
    """Remove one tenant member from the tenant organization and clear tenant-local assignments."""
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ApiError(
            error_code="invalid_member",
            message="Username is required.",
            status_code=400,
        )

    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    member = _tenant_member_or_error(tenant_ref, tenant.slug, normalized_username)
    local_user = _upsert_local_member_or_error(member, normalized_username)

    _directory_admin().remove_member(username=normalized_username, tenant_ref=tenant_ref)
    _clear_local_tenant_assignments(local_user, tenant.id)
    return normalized_username


def add_tenant_group_member(tenant_id: str, username: str, group_name: str) -> dict[str, Any]:
    """Assign one tenant member to one existing organization group and mirror mapped roles locally."""
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ApiError(
            error_code="invalid_member",
            message="Username is required.",
            status_code=400,
        )

    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    validated_group_names = _validated_group_names(tenant_ref, [group_name])
    member = _tenant_member_or_error(tenant_ref, tenant.slug, normalized_username)

    _directory_admin().add_group_member(
        _group_for(organization_id, validated_group_names[0]),
        username=normalized_username,
    )

    _local_user, roles = _sync_local_member_from_keycloak_member(
        tenant,
        tenant_ref,
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

    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    validated_group_names = _validated_group_names(tenant_ref, [group_name])
    member = _tenant_member_or_error(tenant_ref, tenant.slug, normalized_username)

    _directory_admin().remove_group_member(
        _group_for(organization_id, validated_group_names[0]),
        username=normalized_username,
    )

    _local_user, roles = _sync_local_member_from_keycloak_member(
        tenant,
        tenant_ref,
        member,
    )
    return _serialize_member(member, roles=roles)


def assign_tenant_group_role(tenant_id: str, group_name: str, role_name: str) -> dict[str, Any]:
    """Grant one tenant-scoped role to one Keycloak organization group and mirror the result locally."""
    normalized_role_name = _normalize_role_name(role_name)
    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    group = _organization_group_or_error(tenant_ref, group_name)

    updated_group = _directory_admin().set_group_roles(
        group,
        roles=sorted({*_roles_for_group(group), normalized_role_name}),
    )

    group_role_lookup = _organization_group_role_lookup(tenant_ref)
    _sync_local_members_for_group(
        tenant,
        tenant_ref,
        updated_group,
        group_role_lookup=group_role_lookup,
    )
    serialized_group = _serialize_group(
        tenant_ref,
        updated_group,
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
    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    group = _organization_group_or_error(tenant_ref, group_name)

    updated_group = _directory_admin().set_group_roles(
        group,
        roles=[
            mapped_role_name
            for mapped_role_name in _roles_for_group(group)
            if mapped_role_name != normalized_role_name
        ],
    )

    group_role_lookup = _organization_group_role_lookup(tenant_ref)
    _sync_local_members_for_group(
        tenant,
        tenant_ref,
        updated_group,
        group_role_lookup=group_role_lookup,
    )
    serialized_group = _serialize_group(
        tenant_ref,
        updated_group,
        group_role_lookup=group_role_lookup,
    )
    if serialized_group is None:
        raise ApiError(
            error_code="invalid_group",
            message=f"Group '{group_name}' could not be serialized after role removal.",
            status_code=500,
        )
    return serialized_group


def delete_tenant_group(tenant_id: str, group_name: str) -> str:
    """Delete one Keycloak organization group and resync affected tenant members."""
    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    group = _organization_group_or_error(tenant_ref, group_name)

    current_members = _directory_admin().list_group_members(group)
    _directory_admin().delete_group(group)

    group_role_lookup = _organization_group_role_lookup(tenant_ref)
    for member in current_members:
        _sync_local_member_from_keycloak_member(
            tenant,
            tenant_ref,
            member,
            group_role_lookup=group_role_lookup,
        )

    return group.identifier or group_name


def assign_tenant_role(tenant_id: str, username: str, role_name: str) -> dict[str, Any]:
    """Assign one tenant-scoped role to one organization member and mirror it locally."""
    normalized_role_name = _normalize_role_name(role_name)
    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    member = _tenant_member_or_error(tenant_ref, tenant.slug, username)

    _directory_admin().assign_roles(
        username=username,
        tenant_ref=tenant_ref,
        roles=[normalized_role_name],
    )

    _local_user, updated_roles = _sync_local_member_from_keycloak_member(
        tenant,
        tenant_ref,
        member,
    )
    return _serialize_member(
        member,
        roles=updated_roles,
    )


def remove_tenant_role(tenant_id: str, username: str, role_name: str) -> dict[str, Any]:
    """Remove one tenant-scoped role from one organization member and mirror it locally."""
    normalized_role_name = _normalize_role_name(role_name)
    tenant, organization_id = _organization_for_tenant(tenant_id)
    tenant_ref = TenantRef(id=organization_id)
    member = _tenant_member_or_error(tenant_ref, tenant.slug, username)

    _directory_admin().remove_roles(
        username=username,
        tenant_ref=tenant_ref,
        roles=[normalized_role_name],
    )

    _local_user, updated_roles = _sync_local_member_from_keycloak_member(
        tenant,
        tenant_ref,
        member,
    )
    return _serialize_member(
        member,
        roles=updated_roles,
    )
