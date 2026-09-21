from __future__ import annotations

from flask import g, jsonify, request

from m8flow_backend.auth import require_current_user
from m8flow_backend.authorization import allow_uri, database_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response


_PERMISSION_CHECK_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


def _normalize_permission_check_method(method: object) -> str | None:
    """Return a supported HTTP verb in canonical form, or ``None``."""
    if not isinstance(method, str):
        return None
    normalized = method.strip().upper()
    return normalized if normalized in _PERMISSION_CHECK_METHODS else None


def permissions_check():
    """Return DB-backed UI permission hints in the core frontend format."""
    user = require_current_user()
    body = request.get_json(silent=True) or {}
    requests_to_check = body.get("requests_to_check")
    if not isinstance(requests_to_check, dict):
        raise ApiError(
            "could_not_requests_to_check",
            "The key 'requests_to_check' not found at root of request body.",
            400,
        )

    session = g.db_session
    results: dict[str, dict[str, bool]] = {}
    for target_uri, methods in requests_to_check.items():
        if not isinstance(target_uri, str) or not isinstance(methods, list):
            continue
        target_results: dict[str, bool] = {}
        for method in methods:
            if not isinstance(method, str):
                continue
            normalized_method = _normalize_permission_check_method(method)
            # Unknown verbs must never fall through to allow_uri's internal
            # action mapping, which also accepts backend-only action names.
            target_results[normalized_method or method.strip().upper()] = (
                normalized_method is not None
                and allow_uri(user, normalized_method, target_uri, session=session)
            )
        results[target_uri] = target_results
    return jsonify({"results": results})

@handle_api_errors
def get_capabilities():
    """Return advisory UI flags from materialized RBAC assignments only.

    This endpoint intentionally does not inspect role names, token claims, or
    authorization fallbacks. The backend permission target and assignment
    tables are the sole source of truth; protected routes still authorize
    every request independently.

    `can_manage_process_models` = may write process-model metadata, including
    the publish lifecycle (draft / published / paused). Computed from the same
    PUT /process-models check `update_process_model` authorizes with, so
    Publish / Pause / Unpublish stay hidden from roles that would get a 403
    instead of being shown and then rejected (M8F-508).
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
            "can_manage_process_models": permitted(
                "PUT", "/v1.0/process-models/capability-check"
            ),
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
