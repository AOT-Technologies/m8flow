from __future__ import annotations

from flask import g
from flask import request

from m8flow_backend.helpers.response_helper import handle_api_errors
from m8flow_backend.helpers.response_helper import success_response
from m8flow_backend.services.tenant_invitation_service import accept_invitation
from m8flow_backend.services.tenant_invitation_service import create_invitation
from m8flow_backend.services.tenant_invitation_service import list_invitations
from m8flow_backend.services.tenant_invitation_service import resend_invitation
from m8flow_backend.services.tenant_invitation_service import revoke_invitation
from m8flow_backend.services.tenant_invitation_service import validate_token
from m8flow_backend.services.tenant_management_authorization import ensure_request_can_access_tenant
from m8flow_backend.services.tenant_management_authorization import require_authorized_user
from m8flow_backend.tenancy import is_super_admin_request
from spiffworkflow_backend.exceptions.api_error import ApiError

DEFAULT_INVITATION_PAGE_SIZE = 10
MAX_INVITATION_PAGE_SIZE = 100


def _require_super_admin(action: str, tenant_id: str):
    """Authorize a super-admin-only invitation action and scope it to the tenant."""
    user = require_authorized_user(
        action,
        tenant_id=tenant_id,
        forbidden_message="Not authorized to manage tenant invitations.",
    )
    if not is_super_admin_request():
        raise ApiError(
            error_code="forbidden",
            message="Only super admins can manage tenant invitations.",
            status_code=403,
        )
    ensure_request_can_access_tenant(
        tenant_id,
        forbidden_message="Not authorized to manage another tenant.",
    )
    return user


def _current_username() -> str:
    user = getattr(g, "user", None)
    return getattr(user, "username", None) or "system"


def _normalized_int_query_arg(name: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
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
def create_tenant_invitation(tenant_id: str):
    """Super Admin: invite a new user to the tenant by email + roles."""
    _require_super_admin("create", tenant_id)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    invitation = create_invitation(
        tenant_id,
        email=payload.get("email"),
        roles=payload.get("roles"),
        validity_days=payload.get("validity_days"),
        created_by=_current_username(),
    )
    return success_response({"tenant_id": tenant_id, "invitation": invitation}, 201)


@handle_api_errors
def list_tenant_invitations(tenant_id: str):
    """Super Admin: list invitations for a tenant (optionally filtered by status)."""
    _require_super_admin("read", tenant_id)
    offset = _normalized_int_query_arg("offset", 0, minimum=0)
    limit = _normalized_int_query_arg(
        "limit", DEFAULT_INVITATION_PAGE_SIZE, minimum=1, maximum=MAX_INVITATION_PAGE_SIZE
    )
    result = list_invitations(
        tenant_id,
        status_filter=request.args.get("status"),
        offset=offset,
        limit=limit,
    )
    return success_response({"tenant_id": tenant_id, **result}, 200)


@handle_api_errors
def resend_tenant_invitation(tenant_id: str, invitation_id: str):
    """Super Admin: rotate the token + expiry of a pending invitation and resend."""
    _require_super_admin("create", tenant_id)
    invitation = resend_invitation(tenant_id, invitation_id, modified_by=_current_username())
    return success_response({"tenant_id": tenant_id, "invitation": invitation}, 200)


@handle_api_errors
def revoke_tenant_invitation(tenant_id: str, invitation_id: str):
    """Super Admin: revoke a pending invitation so its link can no longer be used."""
    _require_super_admin("delete", tenant_id)
    invitation = revoke_invitation(tenant_id, invitation_id, modified_by=_current_username())
    return success_response({"tenant_id": tenant_id, "invitation": invitation}, 200)


@handle_api_errors
def validate_invitation():
    """Public: validate an invitation token and return safe metadata for the accept page."""
    token = request.args.get("token")
    return success_response(validate_token(token), 200)


@handle_api_errors
def accept_tenant_invitation():
    """Public: accept an invitation by setting a password, creating + activating the account."""
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    result = accept_invitation(payload.get("token"), payload.get("password"))
    return success_response(result, 200)
