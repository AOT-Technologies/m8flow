"""Connector templates and tenant connector profiles.

Templates are code. Profile responses never include secret values — only
``configured_secrets`` (the field names that have one stored).
"""

from __future__ import annotations

from typing import Any

import flask.wrappers
from flask import g, jsonify, make_response, request

from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.auth import require_current_user
from m8flow_backend.connectors import service as profiles
from m8flow_backend.connectors.templates import all_templates, template_for
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors
from m8flow_backend.auth import require_tenant_id


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _body() -> dict[str, Any]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("missing_content", "A JSON request body is required.", 400)
    return body


def _current_user_id() -> int:
    user = require_current_user()
    return int(getattr(user, "id", 0) or 0)


@handle_api_errors
@require_permission(forbidden_message="Not allowed to read connector templates")
def connector_template_list() -> flask.wrappers.Response:
    require_current_user()
    return make_response(jsonify(all_templates()), 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/m8flow/connector-templates/{connector_type}",
    forbidden_message="Not allowed to read connector templates",
)
def connector_template_show(connector_type: str) -> flask.wrappers.Response:
    require_current_user()
    template = template_for(connector_type)
    if template is None:
        raise ApiError(
            "not_found", f"Unknown connector type '{connector_type}'.", 404
        )
    return make_response(jsonify(template), 200)


@handle_api_errors
@require_permission(forbidden_message="Not allowed to read connector profiles")
def connector_profile_list(
    connector_type: str | None = None, include_inactive: Any = True
) -> flask.wrappers.Response:
    user = require_current_user()
    tenant_id = require_tenant_id(user)
    include = _as_bool(include_inactive, True)
    rows = profiles.list_profiles(
        g.db_session,
        tenant_id=tenant_id,
        connector_type=connector_type or None,
        include_inactive=include,
    )
    return make_response(jsonify([row.to_dict() for row in rows]), 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/m8flow/connector-profiles/{profile_id}",
    on_deny="404",
    forbidden_message="Connector profile not found",
)
def connector_profile_show(profile_id: int) -> flask.wrappers.Response:
    user = require_current_user()
    tenant_id = require_tenant_id(user)
    profile = profiles.get_profile(
        g.db_session, tenant_id=tenant_id, profile_id=int(profile_id)
    )
    return make_response(jsonify(profile.to_dict()), 200)


@handle_api_errors
@require_permission(
    forbidden_message="Not allowed to manage connector profiles",
    group_fallback=False,
)
def connector_profile_create() -> flask.wrappers.Response:
    user = require_current_user()
    tenant_id = require_tenant_id(user)
    profile = profiles.create_profile(
        g.db_session,
        tenant_id=tenant_id,
        body=_body(),
        user_id=_current_user_id(),
    )
    return make_response(jsonify(profile.to_dict()), 201)


@handle_api_errors
@require_permission(
    uri="/v1.0/m8flow/connector-profiles/{profile_id}",
    forbidden_message="Not allowed to manage connector profiles",
    group_fallback=False,
)
def connector_profile_update(profile_id: int) -> flask.wrappers.Response:
    user = require_current_user()
    tenant_id = require_tenant_id(user)
    profile = profiles.update_profile(
        g.db_session,
        tenant_id=tenant_id,
        profile_id=int(profile_id),
        body=_body(),
        user_id=_current_user_id(),
    )
    return make_response(jsonify(profile.to_dict()), 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/m8flow/connector-profiles/{profile_id}",
    forbidden_message="Not allowed to manage connector profiles",
    group_fallback=False,
)
def connector_profile_delete(
    profile_id: int, hard: Any = False
) -> flask.wrappers.Response:
    user = require_current_user()
    tenant_id = require_tenant_id(user)
    if _as_bool(hard, False):
        profiles.delete_profile(
            g.db_session, tenant_id=tenant_id, profile_id=int(profile_id)
        )
        return make_response(jsonify({"ok": True}), 200)
    profile = profiles.deactivate_profile(
        g.db_session, tenant_id=tenant_id, profile_id=int(profile_id)
    )
    return make_response(jsonify(profile.to_dict()), 200)
