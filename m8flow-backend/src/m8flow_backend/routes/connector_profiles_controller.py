"""Connector templates (schemas) and connector profiles (tenant CRUD).

Templates are code, so they are the same for every tenant and carry nothing
sensitive. Profiles are tenant data; no response from this module ever contains
a secret value -- only ``configured_secrets``, the names of the fields that have
one stored.
"""

from __future__ import annotations

import logging
from typing import Any

import flask.wrappers
from flask import g, jsonify, make_response, request
from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.connectors.descriptor import to_descriptor
from m8flow_backend.connectors.registry import all_connectors, get_connector
from m8flow_backend.services.connector_profile_migration import (
    seed_all_default_profiles,
    seed_default_profile,
)
from m8flow_backend.services.connector_profile_service import (
    ConnectorProfileError,
    ConnectorProfileService,
)

logger = logging.getLogger(__name__)


def _current_user_id() -> int | None:
    user = getattr(g, "user", None)
    return getattr(user, "id", None) if user is not None else None


def _may_write_profiles() -> bool:
    """Whether the caller could create a profile themselves.

    Seeding is a write, so it is only attempted for a caller who is allowed to
    perform one. Any failure to determine this answers "no": declining to seed
    is harmless, seeding without permission is not.
    """
    from spiffworkflow_backend.services.authorization_service import (
        AuthorizationService,
    )

    user = getattr(g, "user", None)
    if user is None:
        return False
    try:
        return AuthorizationService.user_has_permission(
            user=user, permission="create", target_uri="/m8flow/connector-profiles"
        )
    except Exception:
        logger.warning("Could not check connector profile write permission", exc_info=True)
        return False


def _as_api_error(error: ConnectorProfileError) -> ApiError:
    """Map a service error onto the API's error contract.

    Field-level validation problems are carried in ``error.errors`` so the form
    can put each message back on the field that caused it.
    """
    return ApiError(
        error_code="connector_profile_error",
        message=error.message,
        status_code=error.status_code,
        error_line=error.errors[0]["msg"] if error.errors else "",
        task_data={"detail": error.errors} if error.errors else {},
    )


def _body() -> dict[str, Any]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError(
            "missing_content", "A JSON request body is required.", status_code=400
        )
    return body


# ------------------------------------------------------------------ templates


def connector_template_list() -> flask.wrappers.Response:
    """Descriptors for every registered connector."""
    return make_response(jsonify([to_descriptor(cls) for cls in all_connectors()]), 200)


def connector_template_show(connector_type: str) -> flask.wrappers.Response:
    definition = get_connector(connector_type)
    if definition is None:
        raise ApiError(
            "not_found", f"Unknown connector type '{connector_type}'.", status_code=404
        )
    return make_response(jsonify(to_descriptor(definition)), 200)


# ------------------------------------------------------------------- profiles


def connector_profile_list(
    connector_type: str | None = None, include_inactive: bool = True
) -> flask.wrappers.Response:
    """The tenant's profiles.

    The modeler passes ``include_inactive=false`` so a deactivated profile
    cannot be picked; the management UI lists everything so an inactive profile
    stays visible and recoverable.
    """
    if _may_write_profiles():
        # First listing carries the tenant's pre-existing fixed-key credentials
        # into a "default" profile, so an existing setup is usable from the
        # modeler straight away. Done here rather than at startup because it
        # reads tenant-scoped secrets and so needs a request context.
        #
        # Both shapes of this call have to seed: the management UI asks for one
        # connector, but the modeler asks for every profile at once with no
        # connector_type -- and seeding only in the filtered case meant opening a
        # diagram never seeded anything, so the dropdown stayed empty until
        # someone happened to visit that connector's page.
        #
        # Gated on write permission even though this is a GET: seeding creates a
        # row and writes secrets, so a read-only caller must not trigger it. A
        # viewer opening the modeler simply sees whatever a manager has seeded.
        # Idempotent and best effort: it never blocks the listing.
        try:
            if connector_type:
                seed_default_profile(connector_type, _current_user_id())
            else:
                seed_all_default_profiles(_current_user_id())
        except Exception:
            logger.warning(
                "Could not seed default connector profiles (connector=%s)",
                connector_type or "all",
                exc_info=True,
            )

    profiles = ConnectorProfileService.list_profiles(
        connector_type, include_inactive=include_inactive
    )
    return make_response(jsonify([profile.to_dict() for profile in profiles]), 200)


def connector_profile_show(profile_id: int) -> flask.wrappers.Response:
    try:
        profile = ConnectorProfileService.get_profile(profile_id)
    except ConnectorProfileError as error:
        raise _as_api_error(error) from error
    return make_response(jsonify(profile.to_dict()), 200)


def connector_profile_create() -> flask.wrappers.Response:
    try:
        profile = ConnectorProfileService.create_profile(_body(), _current_user_id())
    except ConnectorProfileError as error:
        raise _as_api_error(error) from error
    return make_response(jsonify(profile.to_dict()), 201)


def connector_profile_update(profile_id: int) -> flask.wrappers.Response:
    try:
        profile = ConnectorProfileService.update_profile(
            profile_id, _body(), _current_user_id()
        )
    except ConnectorProfileError as error:
        raise _as_api_error(error) from error
    return make_response(jsonify(profile.to_dict()), 200)


def connector_profile_delete(profile_id: int, hard: bool = False) -> flask.wrappers.Response:
    """Deactivate by default; remove permanently with ``?hard=true``.

    Soft delete is the default because a process model may still name the
    profile: deactivating makes that fail loudly and stays reversible, whereas a
    hard delete also destroys the stored credentials.
    """
    try:
        if hard:
            ConnectorProfileService.delete_profile(profile_id)
            return make_response(jsonify({"ok": True}), 200)
        profile = ConnectorProfileService.deactivate_profile(profile_id)
    except ConnectorProfileError as error:
        raise _as_api_error(error) from error
    return make_response(jsonify(profile.to_dict()), 200)


def connector_profile_set_default(profile_id: int) -> flask.wrappers.Response:
    try:
        profile = ConnectorProfileService.set_default(profile_id)
    except ConnectorProfileError as error:
        raise _as_api_error(error) from error
    return make_response(jsonify(profile.to_dict()), 200)
