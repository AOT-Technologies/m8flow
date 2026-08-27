"""Require an explicit tenant before super-admin workflow authoring writes."""
from __future__ import annotations

from flask import g
from flask import request

from m8flow_backend.tenancy import is_concrete_tenant_id
from m8flow_backend.tenancy import is_super_admin_request

_WORKFLOW_WRITE_OPERATIONS = frozenset(
    {
        "process_group_create",
        "process_group_delete",
        "process_group_move",
        "process_group_update",
        "process_model_copy",
        "process_model_create",
        "process_model_create_with_natural_language",
        "process_model_delete",
        "process_model_file_create",
        "process_model_file_delete",
        "process_model_file_update",
        "process_model_import",
        "process_model_move",
        "process_model_publish",
        "process_model_test_generate",
        "process_model_test_run",
        "process_model_update",
    }
)


def _workflow_write_operation_name() -> str | None:
    endpoint = request.endpoint
    if not isinstance(endpoint, str):
        return None
    operation_name = endpoint.rsplit(".", maxsplit=1)[-1]
    return operation_name if operation_name in _WORKFLOW_WRITE_OPERATIONS else None


def enforce_super_admin_workflow_write_tenant() -> None:
    """Reject super-admin workflow writes made without a concrete tenant."""
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    if not is_super_admin_request() or _workflow_write_operation_name() is None:
        return

    tenant_id = getattr(g, "m8flow_tenant_id", None)
    if is_concrete_tenant_id(tenant_id):
        return

    from spiffworkflow_backend.exceptions.api_error import ApiError

    raise ApiError(
        "tenant_required",
        "Select a tenant before creating, updating, or executing a workflow.",
        status_code=400,
    )


def apply(flask_app) -> None:
    """Register the centralized guard after tenant resolution is installed."""
    if getattr(flask_app, "_m8flow_workflow_write_guard_registered", False):
        return
    flask_app.before_request(enforce_super_admin_workflow_write_tenant)
    flask_app._m8flow_workflow_write_guard_registered = True
