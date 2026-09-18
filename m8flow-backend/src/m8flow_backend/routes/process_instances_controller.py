from __future__ import annotations

from flask import g, request
from sqlalchemy import select

from m8flow_backend import workflow
from m8flow_backend.auth import require_current_user
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_backend.auth import require_tenant_id, resolve_read_tenant_id

_EMPTY_PAGE = {"results": [], "pagination": {"count": 0, "total": 0, "pages": 0}}


def _attach_tenant_names(session, rows) -> None:
    """Add `tenant_name` to cross-tenant rows so the UI can tell them apart.

    Only called on all-tenants reads, so the normal tenant-scoped path costs
    no extra query. Same lookup as home_controller's recent-instances list.
    """
    from m8flow_bpmn_core.models.tenant import M8flowTenantModel

    tenant_ids = {row.get("tenant_id") for row in rows if row.get("tenant_id")}
    if not tenant_ids:
        return
    name_by_id = {
        tenant.id: tenant.name
        for tenant in session.scalars(
            select(M8flowTenantModel).where(M8flowTenantModel.id.in_(tenant_ids))
        )
    }
    for row in rows:
        tid = row.get("tenant_id")
        if tid:
            row["tenant_name"] = name_by_id.get(tid) or tid


def _instance_or_404(session, process_instance_id: int, tenant_id: str | None):
    """Load an instance and enforce tenant scoping, or 404.

    ``tenant_id`` None means "all tenants" -- only ever produced by
    ``resolve_read_tenant_id`` for a verified super-admin, so no tenant
    predicate is applied then. Returns the instance so callers can re-key
    their follow-up reads onto its own concrete tenant.

    Replaces the identical three-line block formerly repeated in every
    instance tab; a fix applied to only one of those left the siblings broken.
    """
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    instance = session.get(ProcessInstanceModel, process_instance_id)
    if instance is None or (tenant_id is not None and instance.m8f_tenant_id != tenant_id):
        raise ApiError("not_found", "Process instance not found", 404)
    return instance


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances",
    on_deny="empty",
    empty_response=_EMPTY_PAGE,
)
def list_process_instances():
    """Designer Process Instances list. A super-admin who selected "All
    Tenants" (no concrete tenant) gets the merged cross-tenant list, with
    each row carrying its own `tenant_id`/`tenant_name`; everyone else is
    tenant-scoped as before. Denied callers get an empty page (200), not 403 —
    mirrors `list_process_models`'s own convention.
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = resolve_read_tenant_id(user)

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
    if tenant_id is None:
        _attach_tenant_names(session, rows)
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
    tenant_id = resolve_read_tenant_id(user)

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
    tenant_id = resolve_read_tenant_id(user)

    detail = workflow.get_instance_detail_for_designer(
        session, tenant_id=tenant_id, process_instance_id=process_instance_id
    )
    if detail is None:
        raise ApiError("not_found", "Process instance not found", 404)
    if tenant_id is None:
        _attach_tenant_names(session, [detail])
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
    user = require_current_user()
    session = g.db_session
    tenant_id = resolve_read_tenant_id(user)

    # Re-key onto the instance's own tenant so the tab readers below stay
    # single-tenant even for an all-tenants super-admin read.
    instance = _instance_or_404(session, process_instance_id, tenant_id)
    tenant_id = instance.m8f_tenant_id

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
    user = require_current_user()
    session = g.db_session
    tenant_id = resolve_read_tenant_id(user)

    # Re-key onto the instance's own tenant so the tab readers below stay
    # single-tenant even for an all-tenants super-admin read.
    instance = _instance_or_404(session, process_instance_id, tenant_id)
    tenant_id = instance.m8f_tenant_id

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
    user = require_current_user()
    session = g.db_session
    tenant_id = resolve_read_tenant_id(user)

    # Re-key onto the instance's own tenant so the tab readers below stay
    # single-tenant even for an all-tenants super-admin read.
    instance = _instance_or_404(session, process_instance_id, tenant_id)
    tenant_id = instance.m8f_tenant_id

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
    user = require_current_user()
    session = g.db_session
    tenant_id = resolve_read_tenant_id(user)

    # Re-key onto the instance's own tenant so the tab readers below stay
    # single-tenant even for an all-tenants super-admin read.
    instance = _instance_or_404(session, process_instance_id, tenant_id)
    tenant_id = instance.m8f_tenant_id

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
    user = require_current_user()
    session = g.db_session
    # Writes stay strict: a lifecycle change must land in exactly one tenant,
    # so no all-tenants relaxation here (resolve_read_tenant_id is read-only).
    tenant_id = require_tenant_id(user)

    _instance_or_404(session, process_instance_id, tenant_id)

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
