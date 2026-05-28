from __future__ import annotations

from flask import g
from flask import request
from m8flow_backend.helpers.response_helper import handle_api_errors
from m8flow_backend.helpers.response_helper import success_response
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
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.authorization_service import AuthorizationService


def _require_authorized_user(action: str):
    user = getattr(g, "user", None)
    if not user:
        raise ApiError(
            error_code="not_authenticated",
            message="User not authenticated",
            status_code=401,
        )

    if not AuthorizationService.user_has_permission(user, action, request.path):
        raise ApiError(
            error_code="forbidden",
            message="Not authorized to manage tenant groups or memberships.",
            status_code=403,
        )
    return user


@handle_api_errors
def list_tenant_members(tenant_id: str):
    """List Keycloak organization members for one tenant with their tenant-local roles."""
    _require_authorized_user("read")
    search = request.args.get("search")
    members = list_tenant_members_with_roles(tenant_id, search=search)
    return success_response(
        {
            "tenant_id": tenant_id,
            "search": search or "",
            "members": members,
        },
        200,
    )


@handle_api_errors
def list_available_tenant_users_for_tenant(tenant_id: str):
    """List existing Keycloak users that can be added to one tenant."""
    _require_authorized_user("read")
    search = request.args.get("search")
    users = list_available_tenant_users(tenant_id, search=search)
    return success_response(
        {
            "tenant_id": tenant_id,
            "search": search or "",
            "users": users,
        },
        200,
    )


@handle_api_errors
def create_tenant_member(tenant_id: str):
    """Add one existing Keycloak user to a tenant organization and optionally assign groups."""
    _require_authorized_user("update")
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
    _require_authorized_user("read")
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
def assign_group_member(tenant_id: str, group_name: str, username: str):
    """Assign one tenant member to one existing organization group."""
    _require_authorized_user("update")
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
    _require_authorized_user("update")
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
    _require_authorized_user("update")
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
    _require_authorized_user("update")
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
    _require_authorized_user("update")
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
    _require_authorized_user("update")
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
