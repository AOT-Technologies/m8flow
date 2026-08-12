from __future__ import annotations

from typing import Any

import flask
from flask import g
from flask import jsonify
from flask import make_response

from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_username
from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_username_prefix
from m8flow_backend.services.tenant_identity_helpers import is_group_for_tenant
from m8flow_backend.services.tenant_identity_helpers import is_global_permission_group_identifier
from m8flow_backend.services.tenant_identity_helpers import qualified_config_group_identifier

_PATCHED = False

DEFAULT_USER_GROUP_CONFIG_KEY = "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"


def _json(payload: Any) -> flask.wrappers.Response:
    return make_response(jsonify(payload), 200)


def _required_username(body: dict[str, Any]) -> str:
    username = body.get("username")
    if not username:
        raise ApiError(
            error_code="username_not_given",
            message="A 'username' value is required in the request body.",
            status_code=400,
        )
    return username


def apply() -> None:
    """Patch user endpoints so username lookups and group listings stay tenant-aware."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.routes import users_controller

    def patched_user_exists_by_username(body: dict[str, Any]) -> flask.wrappers.Response:
        """Report whether the username exists within the current tenant scope."""
        matches = find_users_for_current_tenant_by_username(_required_username(body))
        return _json({"user_found": len(matches) > 0})

    def patched_user_search(username_prefix: str) -> flask.wrappers.Response:
        """Return username-prefix matches scoped to the current tenant."""
        return _json(
            {
                "users": find_users_for_current_tenant_by_username_prefix(username_prefix),
                "username_prefix": username_prefix,
            }
        )

    def patched_user_group_list_for_current_user() -> flask.wrappers.Response:
        """List the current user's groups for the active tenant, hiding the default group."""
        tenant_id = current_tenant_id_or_none()
        default_group = qualified_config_group_identifier(DEFAULT_USER_GROUP_CONFIG_KEY)

        def is_visible(identifier: str) -> bool:
            if default_group is not None and identifier == default_group:
                return False
            if tenant_id is None:
                return True
            return is_group_for_tenant(identifier, tenant_id) or is_global_permission_group_identifier(
                identifier
            )

        visible = sorted(grp.identifier for grp in g.user.groups if is_visible(grp.identifier))
        return _json(visible)

    users_controller.user_exists_by_username = patched_user_exists_by_username
    users_controller.user_search = patched_user_search
    users_controller.user_group_list_for_current_user = patched_user_group_list_for_current_user
    _PATCHED = True
