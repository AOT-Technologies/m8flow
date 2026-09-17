from __future__ import annotations

from flask import g

from m8flow_backend.auth import require_current_user
from m8flow_backend.authorization import database_permission
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response


@handle_api_errors
def get_capabilities():
    """Return advisory UI flags from materialized RBAC assignments only.

    This endpoint intentionally does not inspect role names, token claims, or
    authorization fallbacks. The backend permission target and assignment
    tables are the sole source of truth; protected routes still authorize
    every request independently.
    """
    user = require_current_user()
    session = g.db_session

    def permitted(method: str, path: str) -> bool:
        return database_permission(user, method, path, session=session)

    # Tenant-admin uses the page target, while super-admin uses the tenant
    # registry target. Check both through the materialized permission tables;
    # do not infer this capability from a role name.
    can_manage_tenant = permitted("GET", "/v1.0/m8flow/tenant-management") or permitted(
        "GET", "/v1.0/m8flow/tenants"
    )

    return success_response(
        {
            # PM:ALL is materialized as /process-models/%; use a representative
            # item path so the DB target's wildcard is evaluated.
            "can_manage_processes": permitted("DELETE", "/v1.0/process-models/capability-check"),
            "can_start_processes": permitted("POST", "/v1.0/process-instances"),
            "can_review_tasks": permitted("POST", "/v1.0/tasks/1"),
            "can_read_secrets": permitted("GET", "/v1.0/secrets"),
            "can_manage_secrets": permitted("DELETE", "/v1.0/secrets"),
            "can_read_connectors": permitted("GET", "/v1.0/m8flow/connectors-grouped"),
            "can_manage_connector_profiles": permitted(
                "POST", "/v1.0/m8flow/connector-profiles"
            ),
            "can_manage_tenant": can_manage_tenant,
        },
        200,
    )
