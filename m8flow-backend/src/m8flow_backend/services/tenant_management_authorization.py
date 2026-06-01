from __future__ import annotations

from collections.abc import Mapping

from flask import g
from flask import request

from m8flow_backend.services.tenant_identity_helpers import tenant_alias_from_payload
from m8flow_backend.services.tenant_identity_helpers import tenant_id_from_payload
from m8flow_backend.tenancy import is_super_admin_request
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.authorization_service import AuthorizationService


def _user_has_super_admin_group(user: object | None) -> bool:
    for group in getattr(user, "groups", []):
        identifier = getattr(group, "identifier", None)
        if isinstance(identifier, str) and identifier.strip() == "super-admin":
            return True
    return False


def _user_is_tenant_admin_or_super_admin(
    user: object,
    tenant_id: str | None = None,
) -> bool:
    """Return True if the user has tenant-admin or super-admin access via group membership.

    Used as a fallback when SpiffWorkflow permissions have not yet been populated in the DB
    (e.g. first login with a multi-org token that defers group sync, or YAML import has not
    run for the current login cycle).
    """
    if is_super_admin_request():
        return True

    from m8flow_backend.services.tenant_identity_helpers import (
        current_tenant_id_or_none,
        current_tenant_identifiers,
    )

    effective_tenant_id = tenant_id or current_tenant_id_or_none()
    if not effective_tenant_id:
        return False

    tenant_ids = current_tenant_identifiers(effective_tenant_id)
    for group in getattr(user, "groups", []):
        identifier = getattr(group, "identifier", None)
        if not isinstance(identifier, str) or not identifier:
            continue
        if identifier == "super-admin":
            return True
        prefix, sep, role = identifier.partition(":")
        if sep and prefix in tenant_ids and role == "tenant-admin":
            return True

    return False


def require_authorized_user(
    action: str,
    *,
    forbidden_message: str,
    tenant_id: str | None = None,
):
    user = getattr(g, "user", None)
    if not user:
        raise ApiError(
            error_code="not_authenticated",
            message="User not authenticated",
            status_code=401,
        )

    if AuthorizationService.user_has_permission(user, action, request.path):
        return user

    # Fallback: check group membership directly.
    # SpiffWorkflow permissions for tenant management may not be in the DB when the
    # user's login deferred the group-sync step (multi-org token) or the YAML import
    # has not run yet for this login cycle.
    if _user_is_tenant_admin_or_super_admin(user, tenant_id=tenant_id):
        return user

    raise ApiError(
        error_code="forbidden",
        message=forbidden_message,
        status_code=403,
    )


def _normalized_request_tenant_identifiers() -> set[str]:
    tenant_identifiers: set[str] = set()

    request_tenant_id = getattr(g, "m8flow_tenant_id", None)
    if isinstance(request_tenant_id, str) and request_tenant_id.strip():
        tenant_identifiers.add(request_tenant_id.strip())

    decoded_token = getattr(g, "_m8flow_decoded_token", None)
    if not isinstance(decoded_token, Mapping):
        return tenant_identifiers

    token_tenant_id = tenant_id_from_payload(decoded_token)
    if isinstance(token_tenant_id, str) and token_tenant_id.strip():
        tenant_identifiers.add(token_tenant_id.strip())

    token_tenant_alias = tenant_alias_from_payload(decoded_token)
    if isinstance(token_tenant_alias, str) and token_tenant_alias.strip():
        tenant_identifiers.add(token_tenant_alias.strip())

    organization_claim = decoded_token.get("organization")
    if isinstance(organization_claim, Mapping):
        for alias, details in organization_claim.items():
            if isinstance(alias, str) and alias.strip():
                tenant_identifiers.add(alias.strip())
            if isinstance(details, Mapping):
                organization_id = details.get("id")
                if isinstance(organization_id, str) and organization_id.strip():
                    tenant_identifiers.add(organization_id.strip())

    explicit_tenant_id = decoded_token.get("m8flow_tenant_id")
    if isinstance(explicit_tenant_id, str) and explicit_tenant_id.strip():
        tenant_identifiers.add(explicit_tenant_id.strip())

    explicit_tenant_alias = decoded_token.get("m8flow_tenant_alias")
    if isinstance(explicit_tenant_alias, str) and explicit_tenant_alias.strip():
        tenant_identifiers.add(explicit_tenant_alias.strip())

    return tenant_identifiers


def _requested_tenant_identifiers(tenant_identifier: str) -> set[str]:
    normalized_tenant_identifier = str(tenant_identifier or "").strip()
    if not normalized_tenant_identifier:
        return set()

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from spiffworkflow_backend.models.db import db

    tenant = (
        db.session.query(M8flowTenantModel)
        .filter(
            (M8flowTenantModel.id == normalized_tenant_identifier)
            | (M8flowTenantModel.slug == normalized_tenant_identifier)
        )
        .one_or_none()
    )
    if tenant is None:
        return {normalized_tenant_identifier}

    requested_identifiers = {normalized_tenant_identifier}
    for value in (tenant.id, tenant.slug):
        if isinstance(value, str) and value.strip():
            requested_identifiers.add(value.strip())
    return requested_identifiers


def ensure_request_can_access_tenant(
    tenant_identifier: str,
    *,
    forbidden_message: str,
) -> None:
    if is_super_admin_request():
        return

    if _user_has_super_admin_group(getattr(g, "user", None)):
        return

    # Master-realm requests are treated as global (no tenant scope).
    # _is_master_super_admin_request() may return False when g.user is not yet
    # populated or when the master-realm token lacks the expected role claim,
    # so we fall back to the global-request flag set by resolve_request_tenant().
    if getattr(g, "_m8flow_global_request", False):
        return

    request_tenant_identifiers = _normalized_request_tenant_identifiers()
    if not request_tenant_identifiers:
        raise ApiError(
            error_code="forbidden",
            message=forbidden_message,
            status_code=403,
        )

    if request_tenant_identifiers.intersection(_requested_tenant_identifiers(tenant_identifier)):
        return

    raise ApiError(
        error_code="forbidden",
        message=forbidden_message,
        status_code=403,
    )
