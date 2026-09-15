from __future__ import annotations

from flask import g, request

from m8flow_backend import workflow
from m8flow_backend.auth import require_current_user
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_backend.auth import require_tenant_id

_EMPTY_PAGE = {"results": [], "pagination": {"count": 0, "total": 0, "pages": 0}}


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances",
    on_deny="empty",
    empty_response=_EMPTY_PAGE,
)
def list_process_instances():
    """Designer Process Instances list. Concrete tenant always required —
    same posture as Processes/Templates (`tenancy.require_tenant_id`): no
    merged all-tenant catalog for super-admins, even though nothing here
    technically forbids it. Denied callers get an empty page (200), not 403 —
    mirrors `list_process_models`'s own convention.
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    status = request.args.get("status") or None
    search = request.args.get("search") or None
    started_by = request.args.get("started_by") or None
    sort = request.args.get("sort") or None
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = max(1, min(int(request.args.get("per_page", 25)), 100))
    except (TypeError, ValueError):
        per_page = 25

    rows, pagination = workflow.list_instances_for_designer(
        session,
        tenant_id=tenant_id,
        status=status,
        search=search,
        started_by=started_by,
        sort=sort,
        page=page,
        per_page=per_page,
    )
    return success_response({"results": rows, "pagination": pagination}, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances",
    on_deny="empty",
    empty_response={"owners": []},
)
def list_process_instance_owners():
    """Distinct process-instance initiators for the tenant — populates the
    Process Instances list's "started by" filter dropdown. Same concrete-
    tenant + permission posture as `list_process_instances`: denied callers
    get an empty list (200), not a 403.
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    owners = workflow.list_instance_owners_for_designer(session, tenant_id=tenant_id)
    return success_response({"owners": owners}, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances/{process_instance_id}",
    on_deny="404",
    forbidden_message="Process instance not found",
)
def get_process_instance(process_instance_id: int):
    """Designer Process Instance detail: metadata + source BPMN XML + per-
    task runtime state (for diagram highlighting). Denied or missing
    instance -> 404 (no existence-hiding distinction needed either way —
    same convention as `get_process_model`).
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    detail = workflow.get_instance_detail_for_designer(
        session, tenant_id=tenant_id, process_instance_id=process_instance_id
    )
    if detail is None:
        raise ApiError("not_found", "Process instance not found", 404)
    return success_response(detail, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances/{process_instance_id}",
    on_deny="404",
    forbidden_message="Process instance not found",
)
def list_process_instance_events(process_instance_id: int):
    """Events tab for one process instance. Same tenant + permission
    posture as ``get_process_instance`` (authorize as GET on the instance,
    not a new URI). Missing or denied instance → 404.
    """
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    instance = session.get(ProcessInstanceModel, process_instance_id)
    if instance is None or instance.m8f_tenant_id != tenant_id:
        raise ApiError("not_found", "Process instance not found", 404)

    rows = workflow.list_instance_events_for_designer(
        session, tenant_id=tenant_id, process_instance_id=process_instance_id
    )
    return success_response({"results": rows}, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances/{process_instance_id}",
    on_deny="404",
    forbidden_message="Process instance not found",
)
def list_process_instance_milestones(process_instance_id: int):
    """Milestones tab: zero or one current last milestone. Same tenant +
    permission as ``get_process_instance``. Missing or denied → 404.
    """
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    instance = session.get(ProcessInstanceModel, process_instance_id)
    if instance is None or instance.m8f_tenant_id != tenant_id:
        raise ApiError("not_found", "Process instance not found", 404)

    rows = workflow.list_instance_milestones_for_designer(
        session, tenant_id=tenant_id, process_instance_id=process_instance_id
    )
    return success_response({"results": rows}, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances/{process_instance_id}",
    on_deny="404",
    forbidden_message="Process instance not found",
)
def list_process_instance_completable_tasks(process_instance_id: int):
    """Tasks I can complete: incomplete human tasks on this instance
    where the current user is a candidate. Same tenant + permission as
    ``get_process_instance``. Missing or denied → 404. Empty ``results``
    when the caller has no candidate tasks (including tenant-admin /
    super-admin who are not themselves candidates).
    """
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    instance = session.get(ProcessInstanceModel, process_instance_id)
    if instance is None or instance.m8f_tenant_id != tenant_id:
        raise ApiError("not_found", "Process instance not found", 404)

    rows = workflow.list_completable_tasks_for_designer(
        session,
        tenant_id=tenant_id,
        process_instance_id=process_instance_id,
        user_id=user.id,
    )
    return success_response({"results": rows}, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances/{process_instance_id}",
    on_deny="404",
    forbidden_message="Process instance not found",
)
def list_process_instance_completed_tasks(process_instance_id: int):
    """Tasks tab: Completed by me and All completed. Same tenant +
    permission as ``get_process_instance``. Missing or denied → 404.
    Task is title + name, not the approval-chain owner ``name``.
    """
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    instance = session.get(ProcessInstanceModel, process_instance_id)
    if instance is None or instance.m8f_tenant_id != tenant_id:
        raise ApiError("not_found", "Process instance not found", 404)

    payload = workflow.list_completed_tasks_for_designer(
        session,
        tenant_id=tenant_id,
        process_instance_id=process_instance_id,
        user_id=user.id,
    )
    return success_response(payload, 200)


def _lifecycle_write(process_instance_id: int, action: str):
    """Terminate / suspend / resume. RBAC is on the three route wrappers
    (POST on the instance URI — YAML create on ``/process-instances/*``).
    Missing or other tenant → 404. Invalid status → 409 from core. Writes
    go through ``workflow``, not ``execute_command`` in this controller.
    """
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    instance = session.get(ProcessInstanceModel, process_instance_id)
    if instance is None or instance.m8f_tenant_id != tenant_id:
        raise ApiError("not_found", "Process instance not found", 404)

    writers = {
        "suspend": workflow.suspend_instance,
        "resume": workflow.resume_instance,
        "terminate": workflow.terminate_instance,
    }
    updated = writers[action](
        session,
        tenant_id=tenant_id,
        process_instance_id=process_instance_id,
        user_id=user.id,
    )
    session.flush()
    return success_response({"id": updated.id, "status": updated.status}, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances/{process_instance_id}",
    forbidden_message="Not permitted to change this process instance",
)
def suspend_process_instance(process_instance_id: int):
    return _lifecycle_write(process_instance_id, "suspend")


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances/{process_instance_id}",
    forbidden_message="Not permitted to change this process instance",
)
def resume_process_instance(process_instance_id: int):
    return _lifecycle_write(process_instance_id, "resume")


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances/{process_instance_id}",
    forbidden_message="Not permitted to change this process instance",
)
def terminate_process_instance(process_instance_id: int):
    return _lifecycle_write(process_instance_id, "terminate")
