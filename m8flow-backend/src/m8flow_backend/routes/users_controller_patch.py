from __future__ import annotations

from typing import Any

import flask
from flask import g
from flask import jsonify
from flask import make_response

from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_username
from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_username_prefix
from m8flow_backend.services.tenant_identity_helpers import qualified_config_group_identifier

_PATCHED = False


def apply() -> None:
    """Patch user endpoints so username lookups and group listings stay tenant-aware."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.routes import users_controller

    def patched_user_exists_by_username(body: dict[str, Any]) -> flask.wrappers.Response:
        """Report whether the username exists within the current tenant scope."""
        if "username" not in body:
            raise ApiError(
                error_code="username_not_given",
                message="Username could not be found in post body.",
                status_code=400,
            )
        username = body["username"]
        found_users = find_users_for_current_tenant_by_username(username)
        return make_response(jsonify({"user_found": len(found_users) > 0}), 200)

    def patched_user_search(username_prefix: str) -> flask.wrappers.Response:
        """Return username-prefix matches scoped to the current tenant."""
        found_users = find_users_for_current_tenant_by_username_prefix(username_prefix)
        response_json = {
            "users": found_users,
            "username_prefix": username_prefix,
        }
        return make_response(jsonify(response_json), 200)

    def patched_user_group_list_for_current_user() -> flask.wrappers.Response:
        """List current-user groups while hiding the tenant-qualified default user group."""
        groups = g.user.groups
        default_group_identifier = qualified_config_group_identifier("SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP")
        group_identifiers = [
            group.identifier
            for group in groups
            if default_group_identifier is None or group.identifier != default_group_identifier
        ]
        return make_response(jsonify(sorted(group_identifiers)), 200)

    users_controller.user_exists_by_username = patched_user_exists_by_username
    users_controller.user_search = patched_user_search
    users_controller.user_group_list_for_current_user = patched_user_group_list_for_current_user
    _PATCHED = True
