from __future__ import annotations

from flask import request
from m8flow_backend.helpers.response_helper import handle_api_errors
from m8flow_backend.helpers.response_helper import success_response
from m8flow_backend.services.tenant_management_authorization import ensure_request_can_access_tenant
from m8flow_backend.services.tenant_management_authorization import require_authorized_user
from m8flow_backend.services.tenant_role_service import create_tenant_group
from m8flow_backend.services.tenant_role_service import add_tenant_group_member
from m8flow_backend.services.tenant_role_service import add_tenant_member
from m8flow_backend.services.tenant_role_service import assign_tenant_group_role
from m8flow_backend.services.tenant_role_service import assign_tenant_role
from m8flow_backend.services.tenant_role_service import list_available_tenant_users
from m8flow_backend.services.tenant_role_service import list_tenant_groups_with_members
from m8flow_backend.services.tenant_role_service import list_tenant_members_with_roles
from m8flow_backend.services.tenant_role_service import remove_tenant_group_member
from m8flow_backend.services.tenant_role_service import remove_tenant_group_role
from m8flow_backend.services.tenant_role_service import remove_tenant_role

DEFAULT_TENANT_MEMBER_PAGE_SIZE = 10
MAX_TENANT_MEMBER_PAGE_SIZE = 100
DEFAULT_TENANT_AVAILABLE_USER_PAGE_SIZE = 10
MAX_TENANT_AVAILABLE_USER_PAGE_SIZE = 100


def _require_authorized_user(action: str, tenant_id: str | None = None):
    user = require_authorized_user(
        action,
        tenant_id=tenant_id,
        forbidden_message="Not authorized to manage tenant groups or memberships.",
    )
    if tenant_id:
        ensure_request_can_access_tenant(
            tenant_id,
            forbidden_message="Not authorized to manage another tenant.",
        )
    return user


def _normalized_int_query_arg(
    name: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    raw_value = request.args.get(name)
    if raw_value is None or not str(raw_value).strip():
        return default

    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError):
        return default

    normalized_value = max(minimum, parsed_value)
    if maximum is not None:
        normalized_value = min(normalized_value, maximum)
    return normalized_value


@handle_api_errors
def list_tenant_members(tenant_id: str):
    """List Keycloak organization members for one tenant with their tenant-local roles."""
    _require_authorized_user("read", tenant_id)
    search = request.args.get("search")
    offset = _normalized_int_query_arg("offset", 0, minimum=0)
    limit = _normalized_int_query_arg(
        "limit",
        DEFAULT_TENANT_MEMBER_PAGE_SIZE,
        minimum=1,
        maximum=MAX_TENANT_MEMBER_PAGE_SIZE,
    )
    members = list_tenant_members_with_roles(
        tenant_id,
        search=search,
        offset=offset,
        max_results=limit + 1,
    )
    has_more = len(members) > limit
    return success_response(
        {
            "tenant_id": tenant_id,
            "search": search or "",
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "members": members[:limit],
        },
        200,
    )


@handle_api_errors
def list_available_tenant_users_for_tenant(tenant_id: str):
    """List existing Keycloak users that can be added to one tenant."""
    _require_authorized_user("read", tenant_id)
    search = request.args.get("search")
    offset = _normalized_int_query_arg("offset", 0, minimum=0)
    limit = _normalized_int_query_arg(
        "limit",
        DEFAULT_TENANT_AVAILABLE_USER_PAGE_SIZE,
        minimum=1,
        maximum=MAX_TENANT_AVAILABLE_USER_PAGE_SIZE,
    )
    users = list_available_tenant_users(
        tenant_id,
        search=search,
        offset=offset,
        max_results=limit + 1,
    )
    has_more = len(users) > limit
    return success_response(
        {
            "tenant_id": tenant_id,
            "search": search or "",
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "users": users[:limit],
        },
        200,
    )


@handle_api_errors
def create_tenant_member(tenant_id: str):
    """Add one existing Keycloak user to a tenant organization and optionally assign groups."""
    _require_authorized_user("create", tenant_id)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    member = add_tenant_member(
        tenant_id,
        username=payload.get("username"),
        group_names=payload.get("group_names"),
    )
    return success_response(
        {
            "tenant_id": tenant_id,
            "member": member,
            "group_names": payload.get("group_names") or [],
        },
        201,
    )


@handle_api_errors
def list_tenant_groups(tenant_id: str):
    """List Keycloak organization groups for one tenant with their members and mapped tenant roles."""
    _require_authorized_user("read", tenant_id)
    search = request.args.get("search")
    groups = list_tenant_groups_with_members(tenant_id, search=search)
    return success_response(
        {
            "tenant_id": tenant_id,
            "search": search or "",
            "groups": groups,
        },
        200,
    )


@handle_api_errors
def create_group(tenant_id: str):
    """Create one Keycloak organization group inside one tenant."""
    _require_authorized_user("create", tenant_id)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    group = create_tenant_group(tenant_id, payload.get("name"))
    return success_response(
        {
            "tenant_id": tenant_id,
            "group": group,
        },
        201,
    )


@handle_api_errors
def assign_group_member(tenant_id: str, group_name: str, username: str):
    """Assign one tenant member to one existing organization group."""
    _require_authorized_user("update", tenant_id)
    member = add_tenant_group_member(tenant_id, username, group_name)
    return success_response(
        {
            "tenant_id": tenant_id,
            "group_name": group_name,
            "username": username,
            "member": member,
        },
        200,
    )


@handle_api_errors
def remove_group_member(tenant_id: str, group_name: str, username: str):
    """Remove one tenant member from one existing organization group."""
    _require_authorized_user("delete", tenant_id)
    member = remove_tenant_group_member(tenant_id, username, group_name)
    return success_response(
        {
            "tenant_id": tenant_id,
            "group_name": group_name,
            "username": username,
            "member": member,
        },
        200,
    )


@handle_api_errors
def assign_group_role(tenant_id: str, group_name: str, role_name: str):
    """Assign one tenant-scoped role to one existing organization group."""
    _require_authorized_user("update", tenant_id)
    group = assign_tenant_group_role(tenant_id, group_name, role_name)
    return success_response(
        {
            "tenant_id": tenant_id,
            "group_name": group_name,
            "role_name": role_name,
            "group": group,
        },
        200,
    )


@handle_api_errors
def remove_group_role(tenant_id: str, group_name: str, role_name: str):
    """Remove one tenant-scoped role from one existing organization group."""
    _require_authorized_user("delete", tenant_id)
    group = remove_tenant_group_role(tenant_id, group_name, role_name)
    return success_response(
        {
            "tenant_id": tenant_id,
            "group_name": group_name,
            "role_name": role_name,
            "group": group,
        },
        200,
    )


@handle_api_errors
def assign_member_role(tenant_id: str, username: str, role_name: str):
    """Assign one tenant-scoped role to one organization member."""
    _require_authorized_user("update", tenant_id)
    member = assign_tenant_role(tenant_id, username, role_name)
    return success_response(
        {
            "tenant_id": tenant_id,
            "username": username,
            "role_name": role_name,
            "member": member,
        },
        200,
    )


@handle_api_errors
def remove_member_role(tenant_id: str, username: str, role_name: str):
    """Remove one tenant-scoped role from one organization member."""
    _require_authorized_user("delete", tenant_id)
    member = remove_tenant_role(tenant_id, username, role_name)
    return success_response(
        {
            "tenant_id": tenant_id,
            "username": username,
            "role_name": role_name,
            "member": member,
        },
        200,
    )
