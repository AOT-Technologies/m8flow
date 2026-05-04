from __future__ import annotations

from flask import g
from flask import request
from m8flow_backend.helpers.response_helper import handle_api_errors
from m8flow_backend.helpers.response_helper import success_response
from m8flow_backend.services.tenant_role_service import assign_tenant_role
from m8flow_backend.services.tenant_role_service import list_tenant_members_with_roles
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
            message="Not authorized to manage tenant members.",
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
