from __future__ import annotations

from typing import Any

from flask import g, request
from sqlalchemy import select

from m8flow_backend import human_task, workflow
from m8flow_backend.auth import require_current_user
from m8flow_backend.authorization import actor_is_super_admin
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_backend.auth import require_tenant_id
from m8flow_backend.auth.tenant_context import (
    tenant_id_from_selected_cookie,
    tenant_override_for_super_admin,
)
from m8flow_bpmn_core.models.human_task import HumanTaskModel
from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel
from m8flow_bpmn_core.models.tenant import M8flowTenantModel
from m8flow_bpmn_core.models.user import UserModel

_EMPTY_PAGE = {"results": [], "pagination": {"page": 1, "per_page": 20, "total": 0}}


def _clamp_page_args() -> tuple[int, int]:
    """page/per_page parsing + clamp, mirroring process_instances_controller."""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = max(1, min(int(request.args.get("per_page", 20)), 100))
    except (TypeError, ValueError):
        per_page = 20
    return page, per_page


def _initiator_name_by_instance(
    session: Any, instance_ids: set[int]
) -> dict[int, str | None]:
    """Process-instance id -> initiator display name (or None). Batched to avoid
    N+1. Ids are globally unique, so no tenant filter is needed for this lookup
    (the caller's rows are already tenant-scoped)."""
    if not instance_ids:
        return {}
    stmt = (
        select(
            ProcessInstanceModel.id,
            UserModel.display_name,
            UserModel.username,
        )
        .outerjoin(UserModel, UserModel.id == ProcessInstanceModel.process_initiator_id)
        .where(ProcessInstanceModel.id.in_(instance_ids))
    )
    out: dict[int, str | None] = {}
    for instance_id, display_name, username in session.execute(stmt):
        out[instance_id] = display_name or username
    return out


def _tenant_name_by_id(session: Any, tenant_ids: set[str]) -> dict[str, str]:
    if not tenant_ids:
        return {}
    tenants = session.scalars(
        select(M8flowTenantModel).where(M8flowTenantModel.id.in_(tenant_ids))
    ).all()
    return {tenant.id: tenant.name for tenant in tenants}


@handle_api_errors
@require_permission(
    uri="/v1.0/tasks",
    on_deny="empty",
    empty_response=_EMPTY_PAGE,
)
def list_task_review():
    """Task Review inbox: the caller's pending human tasks (super-admin: every
    tenant's, optionally scoped with ?tenantId=). Denied callers get an empty
    page (200), not a 403 -- same posture as list_process_instances. Non-super-
    admins need the m8flow_selected_tenant cookie (own active tenant only).
    """
    user = require_current_user()
    session = g.db_session
    super_admin = actor_is_super_admin(user)
    page, per_page = _clamp_page_args()

    own_tenant_id = tenant_id_from_selected_cookie()
    if not super_admin and not own_tenant_id:
        raise ApiError("tenant_required", "m8flow_selected_tenant cookie is required", 400)
    if own_tenant_id:
        g.m8flow_tenant_id = own_tenant_id
    override = tenant_override_for_super_admin(is_super_admin=super_admin)
    scope_tenant_id = (override or None) if super_admin else own_tenant_id

    if super_admin:
        rows = workflow.list_pending_tasks_for_super_admin(session)
        if scope_tenant_id:
            rows = [row for row in rows if row.m8f_tenant_id == scope_tenant_id]
    else:
        # limit is capped at 50 in the helper; Python-slice for page/per_page.
        rows = workflow.list_pending_tasks_for_user(
            session, tenant_id=scope_tenant_id, user_id=user.id, limit=50
        )

    total = len(rows)
    start = (page - 1) * per_page
    page_rows = rows[start : start + per_page]

    initiator_by_instance = _initiator_name_by_instance(
        session, {row.process_instance_id for row in page_rows}
    )
    name_by_tenant = _tenant_name_by_id(session, {row.m8f_tenant_id for row in page_rows})

    results = [
        {
            "id": row.id,
            "task_title": row.task_title,
            "task_name": row.task_name,
            "process_model_display_name": row.process_model_display_name,
            "process_instance_id": row.process_instance_id,
            "submitted_by": initiator_by_instance.get(row.process_instance_id),
            "status": row.task_status,
            "created_at_in_seconds": row.created_at_in_seconds,
            "tenant_name": name_by_tenant.get(row.m8f_tenant_id) or row.m8f_tenant_id,
        }
        for row in page_rows
    ]
    return success_response(
        {"results": results, "pagination": {"page": page, "per_page": per_page, "total": total}},
        200,
    )


@handle_api_errors
@require_permission(
    uri="/v1.0/tasks/{human_task_id}",
    on_deny="404",
    forbidden_message="Task not found",
)
def get_task_review(human_task_id: int):
    """Composite Task Review detail: task header + form + outcomes + approval
    chain + activity feed + instance summary. Denied or not-visible/missing
    (including other-tenant) -> 404, mirroring the bare GET /v1.0/tasks/{id}
    route (require_permission on_deny="404") and get_process_instance.
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    task = session.get(HumanTaskModel, human_task_id)
    if task is None or task.m8f_tenant_id != tenant_id:
        raise ApiError("not_found", "Task not found", 404)

    instance_row = session.execute(
        select(ProcessInstanceModel, UserModel.display_name, UserModel.username)
        .outerjoin(UserModel, UserModel.id == ProcessInstanceModel.process_initiator_id)
        .where(
            ProcessInstanceModel.id == task.process_instance_id,
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
        )
    ).first()
    instance = instance_row[0] if instance_row is not None else None
    submitted_by = (instance_row[1] or instance_row[2]) if instance_row is not None else None

    form = human_task.form_schema_for_task(session, tenant_id=tenant_id, human_task=task)
    outcomes = human_task.outcomes_for_task(
        session, tenant_id=tenant_id, human_task_id=human_task_id
    )
    approval_chain = workflow.list_human_tasks_for_instance(
        session, tenant_id=tenant_id, process_instance_id=task.process_instance_id
    )
    activity = workflow.list_instance_events(
        session, tenant_id=tenant_id, process_instance_id=task.process_instance_id
    )

    instance_payload: dict[str, Any] = {
        "id": task.process_instance_id,
        "status": instance.status if instance is not None else None,
        "start_in_seconds": instance.start_in_seconds if instance is not None else None,
        "last_milestone_bpmn_name": (
            instance.last_milestone_bpmn_name if instance is not None else None
        ),
        "detail_path": f"/process-instances/{task.process_instance_id}",
    }

    payload = {
        "task": {
            "id": task.id,
            "task_title": task.task_title,
            "task_name": task.task_name,
            "task_type": task.task_type,
            "status": task.task_status,
            "completed": task.completed,
            "process_model_display_name": task.process_model_display_name,
            "bpmn_process_identifier": task.bpmn_process_identifier,
            "submitted_by": submitted_by,
            "created_at_in_seconds": task.created_at_in_seconds,
        },
        "form": form,
        "outcomes": outcomes,
        "approval_chain": approval_chain,
        "activity": activity,
        "instance": instance_payload,
    }
    return success_response(payload, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/tasks/{human_task_id}",
    forbidden_message="Not allowed to submit this task",
)
def submit_task_review(human_task_id: int):
    """Submit a Task Review: atomic claim-then-complete via
    human_task.submit_external_form. Body is the filled-in task form (its schema
    fields) plus the reserved `outcome` gateway variable -> task_payload (null
    values dropped). forbidden -> 403, not-visible -> 404, already-completed /
    invalid state -> 409 (mapped from BpmnCoreError via workflow.complete).

    Authorizes against `/tasks/{id}` -- the SAME uri core's claim/complete
    authorize on (`require_command_authorization(target_uri="/tasks/{id}")`), so
    the route gate mirrors the domain grant exactly. Gating on the stricter
    `/tasks/{id}/complete` sub-uri instead falsely denied editor/reviewer/
    submitter, whose `manage-tasks` grant (m8flow.yml, actions [all]) is on
    `/tasks/*` -- claim/complete succeed for them, so the route must too. The
    authoritative RBAC (command authorization + task-assignment check) still
    runs inside submit_external_form; this is defense-in-depth, not the gate.
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    task = session.get(HumanTaskModel, human_task_id)
    if task is None or task.m8f_tenant_id != tenant_id:
        raise ApiError("not_found", "Task not found", 404)

    body = request.get_json(silent=True) or {}
    # Forward the whole submitted form as the task payload: the task's own form
    # fields (rendered from its JSON schema) plus the reserved `outcome` gateway
    # variable when an outcome was chosen. Null values are dropped so an unset
    # optional field doesn't overwrite existing task data. There is no special
    # "comment" key -- a comment is just a form field when the schema defines one.
    task_payload: dict[str, Any] = {
        key: value for key, value in body.items() if value is not None
    }

    # submit_external_form (claim-then-complete) returns the HumanTaskModel that
    # core's complete_task produces -- NOT the ProcessInstanceModel -- so resolve
    # the instance explicitly for its id + advanced status (the contract's
    # {process_instance_id, status}).
    completed_task = human_task.submit_external_form(
        session,
        tenant_id=tenant_id,
        human_task_id=human_task_id,
        user_id=user.id,
        task_payload=task_payload or None,
    )
    process_instance_id = completed_task.process_instance_id
    instance = session.get(ProcessInstanceModel, process_instance_id)
    process_status = instance.status if instance is not None else None
    process_complete = process_status == "complete"
    # A 200 already means the task was completed; spell it out so the response
    # doesn't read as a failure just because the *process* status is an ongoing
    # state like "user_input_required" (the workflow advanced to its next step).
    message = (
        "Task completed. The process is now complete."
        if process_complete
        else "Task completed. The process has advanced to the next step."
    )
    return success_response(
        {
            "process_instance_id": process_instance_id,
            "process_status": process_status,
            "process_complete": process_complete,
            "message": message,
        },
        200,
    )
