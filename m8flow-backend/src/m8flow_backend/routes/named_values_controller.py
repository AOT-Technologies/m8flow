"""HTTP handlers for tenant-scoped named configuration variables."""

from __future__ import annotations

from typing import Any

import flask.wrappers
from flask import g, jsonify, make_response, request

from m8flow_backend.auth import require_current_user, require_tenant_id
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors
from m8flow_backend.secrets import named_values

_COLLECTION_URI = "/v1.0/m8flow/named-values"
_ITEM_URI = "/v1.0/m8flow/named-values/{variable_id}"


def _body() -> dict[str, Any]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("missing_content", "A JSON request body is required.", 400)
    return body


@handle_api_errors
@require_permission(
    uri=_COLLECTION_URI,
    forbidden_message="Not allowed to read configuration variables",
    group_fallback=False,
)
def named_value_list() -> flask.wrappers.Response:
    user = require_current_user()
    tenant_id = require_tenant_id(user)
    rows = named_values.list_named_values(g.db_session, tenant_id=tenant_id)
    return make_response(jsonify(rows), 200)


@handle_api_errors
@require_permission(
    uri=_COLLECTION_URI,
    forbidden_message="Not allowed to manage configuration variables",
    group_fallback=False,
)
def named_value_create() -> flask.wrappers.Response:
    user = require_current_user()
    row = named_values.create_named_value(
        g.db_session,
        tenant_id=require_tenant_id(user),
        body=_body(),
        user_id=int(getattr(user, "id", 0) or 0),
    )
    return make_response(jsonify(row), 201)


@handle_api_errors
@require_permission(
    uri=_ITEM_URI,
    on_deny="404",
    forbidden_message="Configuration variable not found",
    group_fallback=False,
)
def named_value_show(variable_id: str) -> flask.wrappers.Response:
    user = require_current_user()
    row = named_values.get_named_value(
        g.db_session,
        tenant_id=require_tenant_id(user),
        variable_id=variable_id,
    )
    return make_response(jsonify(row), 200)


@handle_api_errors
@require_permission(
    uri=_ITEM_URI,
    forbidden_message="Not allowed to manage configuration variables",
    group_fallback=False,
)
def named_value_update(variable_id: str) -> flask.wrappers.Response:
    user = require_current_user()
    row = named_values.update_named_value(
        g.db_session,
        tenant_id=require_tenant_id(user),
        variable_id=variable_id,
        body=_body(),
        user_id=int(getattr(user, "id", 0) or 0),
    )
    return make_response(jsonify(row), 200)


@handle_api_errors
@require_permission(
    uri=_ITEM_URI,
    forbidden_message="Not allowed to manage configuration variables",
    group_fallback=False,
)
def named_value_delete(variable_id: str) -> flask.wrappers.Response:
    user = require_current_user()
    named_values.delete_named_value(
        g.db_session,
        tenant_id=require_tenant_id(user),
        variable_id=variable_id,
    )
    return make_response(jsonify({"ok": True}), 200)
