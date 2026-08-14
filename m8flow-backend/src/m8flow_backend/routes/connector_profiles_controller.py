"""Connector templates (schemas) and connector profiles (per-tenant credential sets).

Nothing here ever returns a secret value. A profile response carries the names
of the secret fields that are configured, not what they hold.
"""

from __future__ import annotations

from typing import Any

import flask.wrappers
from flask import g, request
from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.connectors.descriptor import all_descriptors, to_descriptor
from m8flow_backend.connectors.registry import get_connector
from m8flow_backend.helpers.response_helper import (
    error_response,
    handle_api_errors,
    success_response,
)
from m8flow_backend.services.connector_profile_service import (
    ConnectorProfileError,
    ConnectorProfileService,
)
from m8flow_backend.tenancy import get_tenant_id


def _current_user_id() -> int | None:
    user = getattr(g, "user", None)
    return getattr(user, "id", None) if user is not None else None


def _require_tenant() -> str:
    """Resolve the active tenant, or fail with an actionable 400."""
    try:
        tenant_id = get_tenant_id()
    except RuntimeError:
        tenant_id = None
    if not tenant_id:
        raise ApiError(
            error_code="tenant_context_required",
            message="An active tenant is required. Select a tenant and try again.",
            status_code=400,
        )
    return tenant_id


def _profile_error_response(exc: ConnectorProfileError) -> flask.wrappers.Response:
    from flask import jsonify, make_response

    payload: dict[str, Any] = {
        "error_code": "connector_profile_error",
        "message": exc.message,
    }
    if exc.errors:
        payload["detail"] = exc.errors
    return make_response(jsonify(payload), exc.status_code)


def connector_template_list() -> flask.wrappers.Response:
    """Every connector schema known to this backend."""
    return success_response(all_descriptors())


def connector_template_show(connector_type: str) -> flask.wrappers.Response:
    definition = get_connector(connector_type)
    if definition is None:
        return error_response(
            "connector_not_found", f"Unknown connector type '{connector_type}'.", 404
        )
    return success_response(to_descriptor(definition))


@handle_api_errors
def connector_profile_list() -> flask.wrappers.Response:
    """Profiles for the active tenant, optionally for one connector."""
    _require_tenant()
    connector_type = request.args.get("connector_type") or request.args.get("connectorType")
    profiles = ConnectorProfileService.list_profiles(connector_type)
    return success_response([profile.to_dict() for profile in profiles])


@handle_api_errors
def connector_profile_show(configuration_id: int) -> flask.wrappers.Response:
    _require_tenant()
    try:
        profile = ConnectorProfileService.get_profile(configuration_id)
    except ConnectorProfileError as exc:
        return _profile_error_response(exc)
    return success_response(profile.to_dict())


@handle_api_errors
def connector_profile_create() -> flask.wrappers.Response:
    _require_tenant()
    body = request.get_json(silent=True) or {}
    try:
        profile = ConnectorProfileService.create_profile(body, _current_user_id())
    except ConnectorProfileError as exc:
        return _profile_error_response(exc)
    return success_response(profile.to_dict(), 201)


@handle_api_errors
def connector_profile_update(configuration_id: int) -> flask.wrappers.Response:
    _require_tenant()
    body = request.get_json(silent=True) or {}
    try:
        profile = ConnectorProfileService.update_profile(configuration_id, body, _current_user_id())
    except ConnectorProfileError as exc:
        return _profile_error_response(exc)
    return success_response(profile.to_dict())


@handle_api_errors
def connector_profile_delete(configuration_id: int) -> flask.wrappers.Response:
    _require_tenant()
    try:
        ConnectorProfileService.delete_profile(configuration_id)
    except ConnectorProfileError as exc:
        return _profile_error_response(exc)
    return success_response({"ok": True})


@handle_api_errors
def connector_profile_set_default(configuration_id: int) -> flask.wrappers.Response:
    _require_tenant()
    try:
        profile = ConnectorProfileService.set_default(configuration_id)
    except ConnectorProfileError as exc:
        return _profile_error_response(exc)
    return success_response(profile.to_dict())
