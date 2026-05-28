from __future__ import annotations

from typing import Any

import flask.wrappers
from flask import current_app
from flask import jsonify
from flask import make_response

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.user_group_assignment import UserGroupAssignmentModel
from spiffworkflow_backend.services.user_service import UserService

from m8flow_backend.config import shared_realm_name
from m8flow_backend.services.keycloak_service import add_organization_group_member
from m8flow_backend.services.keycloak_service import get_organization_by_alias
from m8flow_backend.services.keycloak_service import get_organization_member_by_username
from m8flow_backend.services.keycloak_service import remove_organization_group_member
from m8flow_backend.services.tenant_group_mapping import (
    VALID_TENANT_ROLE_NAMES,
    organization_group_name_candidates_for_tenant_role,
)
from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.services.tenant_identity_helpers import current_tenant_identifiers
from m8flow_backend.services.tenant_identity_helpers import is_group_for_tenant
from m8flow_backend.services.tenant_identity_helpers import realm_from_service
from m8flow_backend.services.tenant_identity_helpers import tenant_slug_for_identifier

_PATCHED = False


def _active_tenant_role_name(group_identifier: str, tenant_id: str) -> str | None:
    """Return the active-tenant role name for one tenant-qualified group identifier."""
    normalized_group_identifier = group_identifier.strip()
    if not normalized_group_identifier or not is_group_for_tenant(normalized_group_identifier, tenant_id):
        return None

    tenant_prefix, separator, role_name = normalized_group_identifier.partition(":")
    if not separator or tenant_prefix not in current_tenant_identifiers(tenant_id):
        return None

    normalized_role_name = role_name.strip()
    if normalized_role_name not in VALID_TENANT_ROLE_NAMES:
        return None
    return normalized_role_name


def _local_assignment_query(user: Any, group: Any, tenant_id: str):
    query = UserGroupAssignmentModel.query.filter_by(user_id=user.id, group_id=group.id)
    if hasattr(UserGroupAssignmentModel, "m8f_tenant_id"):
        query = query.filter_by(m8f_tenant_id=tenant_id)
    return query


def _create_local_assignment(user: Any, group: Any, tenant_id: str) -> Any:
    assignment = _local_assignment_query(user, group, tenant_id).first()
    if assignment is not None:
        return assignment

    kwargs: dict[str, Any] = {"user_id": user.id, "group_id": group.id}
    if hasattr(UserGroupAssignmentModel, "m8f_tenant_id"):
        kwargs["m8f_tenant_id"] = tenant_id
    assignment = UserGroupAssignmentModel(**kwargs)
    db.session.add(assignment)
    db.session.commit()
    return assignment


def _delete_local_assignment(user: Any, group: Any, tenant_id: str) -> Any | None:
    assignment = _local_assignment_query(user, group, tenant_id).first()
    if assignment is None:
        return None

    db.session.delete(assignment)
    db.session.commit()
    return assignment


def _shared_realm_user(user: Any) -> bool:
    """Return whether the local user row comes from the configured shared realm."""
    return realm_from_service(getattr(user, "service", None)) == shared_realm_name()


def _organization_id_for_tenant(tenant_id: str) -> str:
    tenant_slug = tenant_slug_for_identifier(tenant_id)
    if not tenant_slug:
        raise ApiError(
            error_code="invalid_tenant",
            message=f"Unable to resolve tenant slug for tenant '{tenant_id}'.",
            status_code=400,
        )

    organization = get_organization_by_alias(tenant_slug)
    if not isinstance(organization, dict):
        raise ApiError(
            error_code="organization_not_found",
            message=f"Organization '{tenant_slug}' could not be found in Keycloak.",
            status_code=404,
        )

    organization_id = organization.get("id")
    if not isinstance(organization_id, str) or not organization_id.strip():
        raise ApiError(
            error_code="organization_not_found",
            message=f"Organization '{tenant_slug}' does not have a valid Keycloak id.",
            status_code=404,
        )
    return organization_id.strip()


def _sync_shared_realm_role_membership(user: Any, role_name: str, tenant_id: str, *, present: bool) -> None:
    """Mirror one tenant-role assignment into the shared realm organization group membership."""
    if not _shared_realm_user(user):
        return

    organization_id = _organization_id_for_tenant(tenant_id)
    member = get_organization_member_by_username(organization_id, user.username)
    if not isinstance(member, dict):
        if present:
            raise ApiError(
                error_code="user_not_in_tenant_organization",
                message=(
                    f"User '{user.username}' is not a member of the current tenant organization "
                    f"and cannot receive the role '{role_name}'."
                ),
                status_code=400,
            )
        return

    member_id = member.get("id")
    if not isinstance(member_id, str) or not member_id.strip():
        raise ApiError(
            error_code="user_not_in_tenant_organization",
            message=f"User '{user.username}' does not have a valid organization membership id.",
            status_code=400,
        )

    group_name_candidates = organization_group_name_candidates_for_tenant_role(role_name)
    if not group_name_candidates:
        return

    if present:
        add_organization_group_member(organization_id, group_name_candidates[0], member_id.strip())
        return

    for group_name in group_name_candidates:
        remove_organization_group_member(organization_id, group_name, member_id.strip())


def _assign_user_to_group_impl(original_fn: Any | None = None) -> flask.wrappers.Response:
    from spiffworkflow_backend.routes import user_blueprint

    tenant_id = current_tenant_id_or_none()
    if tenant_id is None:
        if original_fn is not None:
            return original_fn()
        raise ApiError(
            error_code="missing_tenant_context",
            message="A tenant context is required when assigning tenant-scoped user roles.",
            status_code=400,
        )

    user = user_blueprint.get_user_from_request()
    group = user_blueprint.get_group_from_request()
    group_identifier = getattr(group, "identifier", None)
    if not isinstance(group_identifier, str) or not is_group_for_tenant(group_identifier, tenant_id):
        raise ApiError(
            error_code="invalid_group",
            message="The selected group does not belong to the active tenant.",
            status_code=400,
        )

    role_name = _active_tenant_role_name(group_identifier, tenant_id)
    if role_name is not None:
        _sync_shared_realm_role_membership(user, role_name, tenant_id, present=True)

    user_group_assignment = _local_assignment_query(user, group, tenant_id).first()
    if user_group_assignment is not None:
        raise ApiError(
            error_code="user_is_already_in_group",
            message=f"User ({user.id}) is already in group ({group.id})",
            status_code=409,
        )

    user_group_assignment = _create_local_assignment(user, group, tenant_id)
    UserService.update_human_task_assignments_for_user(
        user,
        new_group_ids={group.id},
        old_group_ids=set(),
    )
    return make_response(jsonify({"id": user_group_assignment.id}), 201)


def _remove_user_from_group_impl(original_fn: Any | None = None) -> flask.wrappers.Response:
    from spiffworkflow_backend.routes import user_blueprint

    tenant_id = current_tenant_id_or_none()
    if tenant_id is None:
        if original_fn is not None:
            return original_fn()
        raise ApiError(
            error_code="missing_tenant_context",
            message="A tenant context is required when removing tenant-scoped user roles.",
            status_code=400,
        )

    user = user_blueprint.get_user_from_request()
    group = user_blueprint.get_group_from_request()
    group_identifier = getattr(group, "identifier", None)
    if not isinstance(group_identifier, str) or not is_group_for_tenant(group_identifier, tenant_id):
        raise ApiError(
            error_code="invalid_group",
            message="The selected group does not belong to the active tenant.",
            status_code=400,
        )

    role_name = _active_tenant_role_name(group_identifier, tenant_id)
    if role_name is not None:
        _sync_shared_realm_role_membership(user, role_name, tenant_id, present=False)

    user_group_assignment = _delete_local_assignment(user, group, tenant_id)
    if user_group_assignment is None:
        raise ApiError(
            error_code="user_not_in_group",
            message=f"User ({user.id}) is not in group ({group.id})",
            status_code=400,
        )

    UserService.update_human_task_assignments_for_user(
        user,
        new_group_ids=set(),
        old_group_ids={group.id},
    )
    return make_response(jsonify({"ok": True}), 200)


def apply(flask_app: object | None = None) -> None:
    """Patch user-group mutation routes to work with tenant-scoped organization roles."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.routes import user_blueprint

    app = flask_app or current_app._get_current_object()

    original_assign_user_to_group = user_blueprint.assign_user_to_group
    original_remove_user_from_group = user_blueprint.remove_user_from_group

    def patched_assign_user_to_group() -> flask.wrappers.Response:
        return _assign_user_to_group_impl(original_fn=original_assign_user_to_group)

    def patched_remove_user_from_group() -> flask.wrappers.Response:
        return _remove_user_from_group_impl(original_fn=original_remove_user_from_group)

    user_blueprint.assign_user_to_group = patched_assign_user_to_group
    user_blueprint.remove_user_from_group = patched_remove_user_from_group

    for endpoint, view_function in list(app.view_functions.items()):
        if endpoint.endswith("assign_user_to_group") or (
            getattr(view_function, "__module__", None) == user_blueprint.__name__
            and getattr(view_function, "__name__", None) == "assign_user_to_group"
        ):
            app.view_functions[endpoint] = patched_assign_user_to_group
        if endpoint.endswith("remove_user_from_group") or (
            getattr(view_function, "__module__", None) == user_blueprint.__name__
            and getattr(view_function, "__name__", None) == "remove_user_from_group"
        ):
            app.view_functions[endpoint] = patched_remove_user_from_group

    _PATCHED = True
