from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import Session

from m8flow_bpmn_core import api
from m8flow_bpmn_core.errors import BpmnCoreError, InvalidStateError
from m8flow_bpmn_core.models.human_task import HumanTaskModel
from m8flow_bpmn_core.models.human_task_user import HumanTaskUserModel
from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel, ProcessInstanceStatus
from m8flow_bpmn_core.models.process_model_bpmn_version import ProcessModelBpmnVersionModel
from m8flow_backend.errors import ApiError, map_bpmn_error
from m8flow_backend.auth import is_super_admin_request
from m8flow_backend.workflow.process_model_tests import run_process_model_tests as run_process_model_tests
from m8flow_backend.workflow.script_unit_tests import (
    add_script_unit_test as add_script_unit_test,
    list_script_unit_tests as list_script_unit_tests,
    run_script_unit_test as run_script_unit_test,
    run_stored_script_unit_test as run_stored_script_unit_test,
)
from m8flow_telemetry.metrics import (
    record_process_instance_created,
    record_process_instance_active_delta,
    record_process_instance_terminal,
    record_task_completed,
)

LOGGER = logging.getLogger(__name__)

_TERMINAL_INSTANCE_STATUSES = frozenset(
    {
        ProcessInstanceStatus.complete.value,
        ProcessInstanceStatus.error.value,
        ProcessInstanceStatus.terminated.value,
        "complete",
        "error",
        "terminated",
    }
)


def _instance_status_value(status: object) -> str:
    value = getattr(status, "value", status)
    return str(value)


def _emit_process_instance_terminal_log(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> str | None:
    """Log duration when an instance has reached a terminal status.

    Used by Grafana Application Metrics (`process instance completed`).
    Returns the status string when a line was emitted, else None.
    """
    instance = session.get(ProcessInstanceModel, process_instance_id)
    if instance is None or instance.m8f_tenant_id != tenant_id:
        return None
    status = _instance_status_value(instance.status)
    if status not in _TERMINAL_INSTANCE_STATUSES:
        return None
    start = instance.start_in_seconds
    end = instance.end_in_seconds or int(time.time())
    duration_seconds = None
    if start is not None:
        duration_seconds = max(0.0, float(end) - float(start))
    LOGGER.info(
        "process instance completed",
        extra={
            "m8flow_tenant_id": tenant_id,
            "process_instance_id": instance.id,
            "process_instance_status": status,
            "duration_seconds": duration_seconds,
            "process_model_identifier": instance.process_model_identifier,
        },
    )
    return status


def _reject_task_write_if_instance_suspended(
    session: Session, *, tenant_id: str, human_task_id: int, action: str
) -> None:
    """Host guard: core claim/complete do not check instance status, so a
    suspended instance would still accept a human-task submit."""
    task = session.get(HumanTaskModel, human_task_id)
    if task is None or task.m8f_tenant_id != tenant_id:
        return
    instance = session.get(ProcessInstanceModel, task.process_instance_id)
    if instance is not None and instance.status == ProcessInstanceStatus.suspended.value:
        raise InvalidStateError(f"Cannot {action} a task on a suspended process instance")


def import_definition(
    session: Session,
    *,
    tenant_id: str,
    user_id: int,
    bpmn_identifier: str,
    source_bpmn_xml: str,
    source_dmn_xml: str | None = None,
    bpmn_name: str | None = None,
    properties_json: dict[str, Any] | None = None,
) -> Any:
    try:
        return api.execute_command(
            session,
            api.ImportBpmnProcessDefinitionCommand(
                tenant_id=tenant_id,
                bpmn_identifier=bpmn_identifier,
                user_id=user_id,
                source_bpmn_xml=source_bpmn_xml,
                source_dmn_xml=source_dmn_xml,
                bpmn_name=bpmn_name,
                properties_json=properties_json,
            ),
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc


def start(
    session: Session,
    *,
    tenant_id: str,
    user_id: int,
    process_model_identifier: str,
    summary: str | None = None,
    submission_metadata: dict[str, Any] | None = None,
) -> ProcessInstanceModel:
    definition_id = _latest_definition_id(
        session, tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    try:
        instance = api.execute_command(
            session,
            api.InitializeProcessInstanceFromDefinitionCommand(
                tenant_id=tenant_id,
                bpmn_process_definition_id=definition_id,
                process_initiator_id=user_id,
                summary=summary,
                submission_metadata=submission_metadata,
                started_at_in_seconds=int(time.time()),
            ),
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc
    except Exception as exc:
        # SpiffWorkflow raises its own parse/validation errors that are not
        # BpmnCoreError — e.g. ValidationException "No start event found." when
        # the model's BPMN can't actually be started. Those are a problem with
        # the process model (a 4xx the caller can act on), not a host 500.
        # Detected by module rather than imported: the host must not import
        # spiffworkflow (see AGENTS.md).
        if type(exc).__module__.split(".", 1)[0] == "SpiffWorkflow":
            raise ApiError(
                "invalid_process_model",
                f"This process model cannot be started: {exc}",
                422,
            ) from exc
        raise
    record_process_instance_created(tenant_id)
    record_process_instance_active_delta(tenant_id, 1)
    return instance


def claim(
    session: Session,
    *,
    tenant_id: str,
    human_task_id: int,
    user_id: int,
) -> HumanTaskModel:
    try:
        _reject_task_write_if_instance_suspended(
            session, tenant_id=tenant_id, human_task_id=human_task_id, action="claim"
        )
        return api.execute_command(
            session,
            api.ClaimTaskCommand(
                tenant_id=tenant_id,
                human_task_id=human_task_id,
                user_id=user_id,
            ),
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc


def complete(
    session: Session,
    *,
    tenant_id: str,
    human_task_id: int,
    user_id: int,
    task_payload: dict[str, Any] | None = None,
) -> ProcessInstanceModel:
    payload = None
    if task_payload is not None:
        payload = {str(key): _stringify_metadata_value(value) for key, value in task_payload.items()}
    try:
        _reject_task_write_if_instance_suspended(
            session, tenant_id=tenant_id, human_task_id=human_task_id, action="complete"
        )
        instance = api.execute_command(
            session,
            api.CompleteTaskCommand(
                tenant_id=tenant_id,
                human_task_id=human_task_id,
                user_id=user_id,
                task_payload=payload,
            ),
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc
    record_task_completed(tenant_id, task_type="UserTask")
    process_instance_id = getattr(instance, "process_instance_id", None)
    if process_instance_id is None:
        process_instance_id = getattr(instance, "id", None)
    if process_instance_id is not None:
        terminal = _emit_process_instance_terminal_log(
            session, tenant_id=tenant_id, process_instance_id=int(process_instance_id)
        )
        if terminal == "complete":
            record_process_instance_terminal(tenant_id, outcome="completed")
    return instance


def suspend_instance(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    user_id: int,
) -> ProcessInstanceModel:
    try:
        return api.execute_command(
            session,
            api.SuspendProcessInstanceCommand(
                tenant_id=tenant_id,
                process_instance_id=process_instance_id,
                user_id=user_id,
            ),
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc


def resume_instance(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    user_id: int,
) -> ProcessInstanceModel:
    try:
        return api.execute_command(
            session,
            api.ResumeProcessInstanceCommand(
                tenant_id=tenant_id,
                process_instance_id=process_instance_id,
                user_id=user_id,
            ),
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc


def terminate_instance(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    user_id: int,
) -> ProcessInstanceModel:
    try:
        instance = api.execute_command(
            session,
            api.TerminateProcessInstanceCommand(
                tenant_id=tenant_id,
                process_instance_id=process_instance_id,
                user_id=user_id,
            ),
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc
    record_process_instance_terminal(tenant_id, outcome="terminated")
    _emit_process_instance_terminal_log(
        session, tenant_id=tenant_id, process_instance_id=instance.id
    )
    return instance


def list_instances(
    session: Session,
    *,
    tenant_id: str,
    status: str | None = None,
) -> list[ProcessInstanceModel]:
    try:
        return api.execute_query(
            session,
            api.ListProcessInstancesQuery(tenant_id=tenant_id, status=status),
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc


def list_pending_tasks(
    session: Session,
    *,
    tenant_id: str,
    user_id: int,
) -> list[HumanTaskModel]:
    try:
        tasks = api.execute_query(
            session,
            api.GetPendingTasksQuery(tenant_id=tenant_id, user_id=user_id),
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc
    if not tasks:
        return tasks
    instance_ids = {task.process_instance_id for task in tasks}
    suspended_ids = set(
        session.scalars(
            select(ProcessInstanceModel.id).where(
                ProcessInstanceModel.id.in_(instance_ids),
                ProcessInstanceModel.m8f_tenant_id == tenant_id,
                ProcessInstanceModel.status == ProcessInstanceStatus.suspended.value,
            )
        )
    )
    return [task for task in tasks if task.process_instance_id not in suspended_ids]


def list_pending_tasks_for_super_admin(session: Session) -> list[HumanTaskModel]:
    if not is_super_admin_request():
        raise ApiError("permission_denied", "Super-admin access required", 403)
    return list(
        session.scalars(
            select(HumanTaskModel)
            .join(ProcessInstanceModel, ProcessInstanceModel.id == HumanTaskModel.process_instance_id)
            .where(
                HumanTaskModel.completed == False,  # noqa: E712
                ProcessInstanceModel.status != ProcessInstanceStatus.suspended.value,
            )
        )
    )


def list_instances_for_super_admin(
    session: Session, *, status: str | None = None
) -> list[ProcessInstanceModel]:
    if not is_super_admin_request():
        raise ApiError("permission_denied", "Super-admin access required", 403)
    stmt = select(ProcessInstanceModel)
    if status is not None:
        stmt = stmt.where(ProcessInstanceModel.status == status)
    return list(session.scalars(stmt))


def count_active_process_instances(session: Session, *, tenant_id: str | None = None) -> int:
    """Home-stats support. m8flow_bpmn_core ships no count/aggregate query
    (every query returns full ORM rows) -- this mirrors
    list_instances_for_super_admin's precedent of a direct, raw ORM query
    that drops the tenant filter entirely when tenant_id is None (meaning
    "all tenants", caller-verified super-admin-only), but reduces
    server-side with COUNT(*) instead of materializing full rows.
    """
    # tenant_id=None (all tenants) is caller-verified-super-admin-only --
    # unlike list_instances_for_super_admin's own is_super_admin_request()
    # guard, deliberately not re-checked here (this is home-stats support,
    # called only from home_controller.get_home_stats after it has already
    # computed super_admin via authorization.actor_is_super_admin(user)).
    stmt = select(func.count()).select_from(ProcessInstanceModel).where(
        ProcessInstanceModel.status.in_(ProcessInstanceModel.active_statuses())
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    return int(session.scalar(stmt) or 0)


def count_error_process_instances(session: Session, *, tenant_id: str | None = None) -> int:
    """Home-stats support -- see count_active_process_instances for the
    "no native aggregate query in core" rationale. Deliberately a raw COUNT
    rather than wrapping ListErrorProcessInstancesQuery + len(): that query
    only ever applies the same trivial status == "error" filter
    (services/process_instances.py), so counting it directly server-side
    avoids fetching full rows just to discard them.
    """
    # tenant_id=None (all tenants) is caller-verified-super-admin-only --
    # see count_active_process_instances for why this isn't re-checked here.
    stmt = select(func.count()).select_from(ProcessInstanceModel).where(
        ProcessInstanceModel.status == ProcessInstanceStatus.error
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    return int(session.scalar(stmt) or 0)


def count_process_instances_completed_today(
    session: Session, *, tenant_id: str | None = None, now: datetime | None = None
) -> int:
    """Home-stats support. "Today" is the server's UTC calendar day --
    m8flow_bpmn_core has no timezone infrastructure anywhere (every
    timestamp is a raw epoch-second integer column), so a per-tenant/user
    local-day boundary is not implemented. Revisit if a tenant needs its
    own local "today" instead of UTC.
    """
    # tenant_id=None (all tenants) is caller-verified-super-admin-only --
    # see count_active_process_instances for why this isn't re-checked here.
    reference = now or datetime.now(timezone.utc)
    start_of_day = int(reference.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    stmt = (
        select(func.count())
        .select_from(ProcessInstanceModel)
        .where(
            ProcessInstanceModel.status == ProcessInstanceStatus.complete,
            ProcessInstanceModel.end_in_seconds.is_not(None),
            ProcessInstanceModel.end_in_seconds >= start_of_day,
        )
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    return int(session.scalar(stmt) or 0)


def average_completion_minutes(session: Session, *, tenant_id: str | None = None) -> float | None:
    """Home-stats support. Average over ALL completed instances (not scoped
    to "today" -- that's count_process_instances_completed_today), using
    start_in_seconds -> end_in_seconds. start_in_seconds is populated once
    the instance actually starts running (m8flow_bpmn_core's
    workflow_runtime.py), not at creation. Returns None (not 0) when there
    are no completed instances yet, so the caller can distinguish "no data"
    from "instantly complete".
    """
    # tenant_id=None (all tenants) is caller-verified-super-admin-only --
    # see count_active_process_instances for why this isn't re-checked here.
    stmt = select(
        func.avg(ProcessInstanceModel.end_in_seconds - ProcessInstanceModel.start_in_seconds)
    ).where(
        ProcessInstanceModel.status == ProcessInstanceStatus.complete,
        ProcessInstanceModel.start_in_seconds.is_not(None),
        ProcessInstanceModel.end_in_seconds.is_not(None),
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    avg_seconds = session.scalar(stmt)
    if avg_seconds is None:
        return None
    return round(float(avg_seconds) / 60, 1)


def list_recent_process_instances(
    session: Session, *, tenant_id: str | None = None, limit: int = 10
) -> list[ProcessInstanceModel]:
    """Home "Recent process instances" support. Newest first by id (monotonic
    creation order). tenant_id=None means all tenants -- caller-verified
    super-admin-only, same convention as the Home-stats count helpers.
    Deliberately a raw ORM select rather than ListProcessInstancesQuery:
    that query always requires a tenant_id and has no limit/order params.
    """
    # tenant_id=None (all tenants) is caller-verified-super-admin-only --
    # see count_active_process_instances for why this isn't re-checked here.
    capped = max(1, min(int(limit), 50))
    stmt = select(ProcessInstanceModel).order_by(ProcessInstanceModel.id.desc()).limit(capped)
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    return list(session.scalars(stmt))


def process_model_run_stats(
    session: Session, *, tenant_id: str
) -> dict[str, dict[str, int | None]]:
    """Per-process-model last_run_in_seconds + runs_30d for the Processes list.

    One grouped query for the tenant. runs_30d counts instances whose
    start_in_seconds falls in the last 30 days (null starts excluded).
    last_run_in_seconds is max(start_in_seconds) (null if never started).
    """
    cutoff = int(time.time()) - 30 * 24 * 60 * 60
    runs_30d_expr = func.coalesce(
        func.sum(
            case(
                (
                    (ProcessInstanceModel.start_in_seconds.is_not(None))
                    & (ProcessInstanceModel.start_in_seconds >= cutoff),
                    1,
                ),
                else_=0,
            )
        ),
        0,
    )
    stmt = (
        select(
            ProcessInstanceModel.process_model_identifier,
            func.max(ProcessInstanceModel.start_in_seconds),
            runs_30d_expr,
        )
        .where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
        .group_by(ProcessInstanceModel.process_model_identifier)
    )
    out: dict[str, dict[str, int | None]] = {}
    for model_id, last_run, runs_30d in session.execute(stmt):
        out[str(model_id)] = {
            "last_run_in_seconds": int(last_run) if last_run is not None else None,
            "runs_30d": int(runs_30d or 0),
        }
    return out


def process_model_detail_stats(
    session: Session, *, tenant_id: str, process_model_identifier: str
) -> dict[str, int | None]:
    """Key numbers for one process model: last_run, running_now, runs_30d."""
    cutoff = int(time.time()) - 30 * 24 * 60 * 60
    active = ProcessInstanceModel.active_statuses()
    last_run = session.scalar(
        select(func.max(ProcessInstanceModel.start_in_seconds)).where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
            ProcessInstanceModel.process_model_identifier == process_model_identifier,
        )
    )
    running_now = session.scalar(
        select(func.count())
        .select_from(ProcessInstanceModel)
        .where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
            ProcessInstanceModel.process_model_identifier == process_model_identifier,
            ProcessInstanceModel.status.in_(active),
        )
    )
    runs_30d = session.scalar(
        select(func.count())
        .select_from(ProcessInstanceModel)
        .where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
            ProcessInstanceModel.process_model_identifier == process_model_identifier,
            ProcessInstanceModel.start_in_seconds.is_not(None),
            ProcessInstanceModel.start_in_seconds >= cutoff,
        )
    )
    return {
        "last_run_in_seconds": int(last_run) if last_run is not None else None,
        "running_now": int(running_now or 0),
        "runs_30d": int(runs_30d or 0),
    }


def count_instances_for_process_model(
    session: Session, *, tenant_id: str, process_model_identifier: str
) -> int:
    """How many process instances (any status) exist for this model in the
    tenant. Guards process-model deletion: the designer blocks deleting a
    model that still has instances rather than orphaning their history/audit
    rows (which reference the model by identifier, not FK)."""
    return int(
        session.scalar(
            select(func.count())
            .select_from(ProcessInstanceModel)
            .where(
                ProcessInstanceModel.m8f_tenant_id == tenant_id,
                ProcessInstanceModel.process_model_identifier == process_model_identifier,
            )
        )
        or 0
    )


def count_instances_for_process_group(
    session: Session, *, tenant_id: str, group_id: str
) -> int:
    """How many process instances exist for models in this group (this id or
    nested under `group_id/`). Guards process-group deletion so run history
    is never orphaned when the group's models are removed from disk."""
    prefix = group_id.rstrip("/") + "/"
    return int(
        session.scalar(
            select(func.count())
            .select_from(ProcessInstanceModel)
            .where(
                ProcessInstanceModel.m8f_tenant_id == tenant_id,
                or_(
                    ProcessInstanceModel.process_model_identifier == group_id,
                    ProcessInstanceModel.process_model_identifier.startswith(prefix),
                ),
            )
        )
        or 0
    )


def list_recent_instances_for_process_model(
    session: Session,
    *,
    tenant_id: str,
    process_model_identifier: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Recent instances for one model. Newest first. Includes starter username."""
    from m8flow_bpmn_core.models.user import UserModel

    capped = max(1, min(int(limit), 50))
    stmt = (
        select(ProcessInstanceModel, UserModel.username)
        .outerjoin(UserModel, UserModel.id == ProcessInstanceModel.process_initiator_id)
        .where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
            ProcessInstanceModel.process_model_identifier == process_model_identifier,
        )
        .order_by(ProcessInstanceModel.id.desc())
        .limit(capped)
    )
    rows: list[dict[str, Any]] = []
    for instance, username in session.execute(stmt):
        duration: int | None = None
        if instance.start_in_seconds is not None and instance.end_in_seconds is not None:
            duration = int(instance.end_in_seconds - instance.start_in_seconds)
        rows.append(
            {
                "id": instance.id,
                "started_by": username or "",
                "start_in_seconds": instance.start_in_seconds,
                "duration_seconds": duration,
                "status": instance.status,
            }
        )
    return rows


def list_instances_for_designer(
    session: Session,
    *,
    tenant_id: str,
    status: str | None = None,
    search: str | None = None,
    started_by: str | None = None,
    sort: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Process Instances page (m8flow-designer). Real filters/pagination —
    NOT a wrapper around `list_instances`/`ListProcessInstancesQuery`
    (m8flow_bpmn_core's own query, `api.execute_query`), which take only
    tenant_id/status and return every matching row unpaginated. Raw ORM
    select instead, same "core has no matching query shape, drop to a
    direct SELECT" precedent as `process_model_run_stats`/
    `list_recent_instances_for_process_model` above.

    `search` matches process_model_display_name/process_model_identifier
    (case-insensitive substring) — no free-text task/summary search, same
    scope as the Templates gallery's own `search` param.

    `started_by` is an exact initiator-username match (the same
    `UserModel.username` this returns as `started_by`); options for the
    UI dropdown come from `list_instance_owners_for_designer`. `sort` is
    an allowlisted key (see `_INSTANCE_SORTS`) — never a raw column name —
    defaulting to newest-first when unset/unknown.
    """
    from m8flow_bpmn_core.models.user import UserModel

    capped_per_page = max(1, min(int(per_page), 100))
    capped_page = max(1, int(page))

    def _apply_filters(stmt: Any) -> Any:
        # UserModel is outer-joined on every statement (count included) so the
        # started_by username filter is applied consistently to both the total
        # and the page.
        stmt = stmt.outerjoin(
            UserModel, UserModel.id == ProcessInstanceModel.process_initiator_id
        ).where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
        if status:
            stmt = stmt.where(ProcessInstanceModel.status == status)
        if started_by:
            stmt = stmt.where(UserModel.username == started_by)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    ProcessInstanceModel.process_model_display_name.ilike(like),
                    ProcessInstanceModel.process_model_identifier.ilike(like),
                )
            )
        return stmt

    count_stmt = _apply_filters(select(func.count()).select_from(ProcessInstanceModel))
    total = int(session.scalar(count_stmt) or 0)
    pages = (total + capped_per_page - 1) // capped_per_page if capped_per_page else 0

    stmt = _apply_filters(select(ProcessInstanceModel, UserModel.username))
    order_by = _INSTANCE_SORTS.get(sort or "", _INSTANCE_SORTS["newest"])()
    stmt = stmt.order_by(*order_by).limit(capped_per_page).offset(
        (capped_page - 1) * capped_per_page
    )

    rows: list[dict[str, Any]] = []
    for instance, username in session.execute(stmt):
        rows.append(
            {
                "id": instance.id,
                "process_model_identifier": instance.process_model_identifier,
                "process_model_display_name": instance.process_model_display_name,
                "status": instance.status,
                "started_by": username or "",
                "start_in_seconds": instance.start_in_seconds,
                "end_in_seconds": instance.end_in_seconds,
            }
        )
    return rows, {"count": len(rows), "total": total, "pages": int(pages)}


# Allowlisted sort keys for list_instances_for_designer -> ORDER BY clauses.
# Deliberately not raw column names off the query string: only these keys are
# honored, anything else falls back to "newest". Each value is a zero-arg
# lambda returning a tuple of ORDER BY expressions (id as a stable tiebreaker
# so equal timestamps/statuses paginate deterministically).
_INSTANCE_SORTS: dict[str, Any] = {
    "newest": lambda: (ProcessInstanceModel.id.desc(),),
    "oldest": lambda: (ProcessInstanceModel.id.asc(),),
    "recent_start": lambda: (
        ProcessInstanceModel.start_in_seconds.desc().nullslast(),
        ProcessInstanceModel.id.desc(),
    ),
    "status": lambda: (
        ProcessInstanceModel.status.asc(),
        ProcessInstanceModel.id.desc(),
    ),
}


def list_instance_owners_for_designer(
    session: Session, *, tenant_id: str
) -> list[str]:
    """Distinct process-initiator usernames for the tenant's process
    instances — feeds the Process Instances page's "started by" filter
    dropdown. Same tenant-scoped, direct-ORM posture as
    `list_instances_for_designer`; usernames only (the filter matches on
    `UserModel.username`), sorted case-insensitively, NULL initiators
    dropped.
    """
    from m8flow_bpmn_core.models.user import UserModel

    stmt = (
        select(UserModel.username)
        .join(
            ProcessInstanceModel,
            ProcessInstanceModel.process_initiator_id == UserModel.id,
        )
        .where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
        .where(UserModel.username.isnot(None))
        .distinct()
    )
    # Sort in Python: Postgres rejects DISTINCT + ORDER BY lower(username)
    # unless lower(username) is also in the select list. SQLite allowed it,
    # so unit tests didn't catch the 500 on GET .../process-instances/owners.
    return sorted(
        (username for (username,) in session.execute(stmt) if username),
        key=str.lower,
    )


def get_instance_detail_for_designer(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> dict[str, Any] | None:
    """Process Instance detail (m8flow-designer): metadata + the source BPMN
    XML (for a bpmn-js diagram) + per-task runtime state, for live
    task-state highlighting on that diagram.

    `bpmn_xml` comes from the instance's own `BpmnProcessDefinitionModel.
    source_bpmn_xml` (the exact definition this instance was started
    from) — None if the instance predates definition tracking or the
    definition was removed; callers render metadata-only in that case.

    Task state: `TaskModel.state` (READY/WAITING/COMPLETED/ERROR/
    CANCELLED/TERMINATED, populated by m8flow_bpmn_core's own
    services/workflow_runtime.py) joined to
    `TaskDefinitionModel.bpmn_identifier` (the literal BPMN XML element
    id) — this join doesn't exist anywhere in m8flow_bpmn_core's own
    query catalog (confirmed: `GetProcessInstanceQuery` returns only the
    bare `ProcessInstanceModel` row, no task list attached), so this is
    new, direct ORM code, not a core query wrapper.
    """
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel
    from m8flow_bpmn_core.models.user import UserModel

    row = session.execute(
        select(ProcessInstanceModel, UserModel.username)
        .outerjoin(UserModel, UserModel.id == ProcessInstanceModel.process_initiator_id)
        .where(
            ProcessInstanceModel.id == process_instance_id,
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
        )
    ).first()
    if row is None:
        return None
    instance, username = row

    bpmn_xml: str | None = None
    if instance.bpmn_process_definition_id is not None:
        definition = session.get(BpmnProcessDefinitionModel, instance.bpmn_process_definition_id)
        if definition is not None and definition.m8f_tenant_id == tenant_id:
            bpmn_xml = definition.source_bpmn_xml

    task_rows = session.execute(
        select(TaskDefinitionModel.bpmn_identifier, TaskModel.state)
        .join(TaskDefinitionModel, TaskDefinitionModel.id == TaskModel.task_definition_id)
        .where(
            TaskModel.process_instance_id == process_instance_id,
            TaskModel.m8f_tenant_id == tenant_id,
        )
    ).all()

    return {
        "id": instance.id,
        "process_model_identifier": instance.process_model_identifier,
        "process_model_display_name": instance.process_model_display_name,
        "status": instance.status,
        "started_by": username or "",
        "start_in_seconds": instance.start_in_seconds,
        "end_in_seconds": instance.end_in_seconds,
        "updated_at_in_seconds": instance.updated_at_in_seconds,
        "last_milestone_bpmn_name": instance.last_milestone_bpmn_name,
        "bpmn_xml": bpmn_xml,
        "tasks": [
            {"bpmn_identifier": bpmn_identifier, "state": state} for bpmn_identifier, state in task_rows
        ],
    }


def list_human_tasks_for_instance(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> list[dict[str, Any]]:
    """Approval chain for a process instance: every human task (completed +
    current), oldest-first. Raw ORM read -- m8flow_bpmn_core exposes no query
    for this shape (its own catalog only returns pending tasks or a bare
    instance row), so this mirrors get_instance_detail_for_designer's
    direct-select + UserModel-join posture.

    `actual_owner_id` and `completed_by_user_id` are bare FK columns (no ORM
    relationships), so UserModel is outer-joined twice under aliases. `name`
    resolves the owner's display name (falling back to the completer's); it is
    None for a system-inactivated task (completed with no human completer and
    no owner). Ordered by `created_at_in_seconds, id` (id is the stable
    tiebreaker -- there is no BPMN step number). `completed_at_in_seconds` is
    `updated_at_in_seconds` for completed rows (core stamps it at completion),
    None while the task is still current.
    """
    from sqlalchemy.orm import aliased

    from m8flow_bpmn_core.models.user import UserModel

    owner = aliased(UserModel)
    completer = aliased(UserModel)
    stmt = (
        select(
            HumanTaskModel,
            owner.display_name,
            owner.username,
            completer.display_name,
            completer.username,
        )
        .outerjoin(owner, owner.id == HumanTaskModel.actual_owner_id)
        .outerjoin(completer, completer.id == HumanTaskModel.completed_by_user_id)
        .where(
            HumanTaskModel.process_instance_id == process_instance_id,
            HumanTaskModel.m8f_tenant_id == tenant_id,
        )
        .order_by(HumanTaskModel.created_at_in_seconds, HumanTaskModel.id)
    )
    rows: list[dict[str, Any]] = []
    for human_task, owner_display, owner_username, completer_display, completer_username in (
        session.execute(stmt)
    ):
        owner_name = owner_display or owner_username
        completer_name = completer_display or completer_username
        rows.append(
            {
                "name": owner_name or completer_name,
                "status": human_task.task_status,
                "completed": human_task.completed,
                "is_current": not human_task.completed,
                "lane_name": human_task.lane_name,
                "completed_at_in_seconds": (
                    human_task.updated_at_in_seconds if human_task.completed else None
                ),
            }
        )
    return rows


def list_instance_events(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> list[dict[str, Any]]:
    """Activity feed for a process instance: the real, ordered event log
    (`ProcessInstanceEventModel`), oldest-first. Replicates core's own
    `get_process_instance_events` select (ordered `timestamp, id`) directly
    rather than going through the query dispatcher.

    `actor_name` resolves the event's user via an outer join (None for system
    events with no user). `task_title` is an optional label from the matching
    `HumanTaskModel` (outer-joined on `task_guid`, tenant-scoped). `event_type`
    is the raw core enum string; presentation is the frontend's job.
    """
    from m8flow_bpmn_core.models.process_instance_event import ProcessInstanceEventModel
    from m8flow_bpmn_core.models.user import UserModel

    stmt = (
        select(
            ProcessInstanceEventModel,
            UserModel.display_name,
            UserModel.username,
            HumanTaskModel.task_title,
        )
        .outerjoin(UserModel, UserModel.id == ProcessInstanceEventModel.user_id)
        .outerjoin(
            HumanTaskModel,
            (HumanTaskModel.task_guid == ProcessInstanceEventModel.task_guid)
            & (HumanTaskModel.m8f_tenant_id == tenant_id),
        )
        .where(
            ProcessInstanceEventModel.process_instance_id == process_instance_id,
            ProcessInstanceEventModel.m8f_tenant_id == tenant_id,
        )
        .order_by(ProcessInstanceEventModel.timestamp, ProcessInstanceEventModel.id)
    )
    rows: list[dict[str, Any]] = []
    for event, actor_display, actor_username, task_title in session.execute(stmt):
        rows.append(
            {
                "event_type": event.event_type,
                "actor_name": actor_display or actor_username,
                "timestamp": float(event.timestamp) if event.timestamp is not None else None,
                "task_guid": event.task_guid,
                "task_title": task_title,
            }
        )
    return rows


def list_instance_events_for_designer(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> list[dict[str, Any]]:
    """Events tab for process instance detail. Same event log and order as
    ``list_instance_events`` (oldest-first), but joins Task → TaskDefinition
    / BpmnProcessDefinition for the mockup BPMN columns. Does not use the
    HumanTask join — that only covers user tasks. Task Review keeps the
    slim reader.
    """
    from m8flow_bpmn_core.models.bpmn_process import BpmnProcessModel
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.process_instance_event import ProcessInstanceEventModel
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel
    from m8flow_bpmn_core.models.user import UserModel

    stmt = (
        select(
            ProcessInstanceEventModel,
            UserModel.display_name,
            UserModel.username,
            BpmnProcessDefinitionModel.bpmn_identifier,
            TaskDefinitionModel.bpmn_name,
            TaskDefinitionModel.bpmn_identifier,
            TaskDefinitionModel.typename,
        )
        .outerjoin(UserModel, UserModel.id == ProcessInstanceEventModel.user_id)
        .outerjoin(
            TaskModel,
            (TaskModel.guid == ProcessInstanceEventModel.task_guid)
            & (TaskModel.m8f_tenant_id == tenant_id)
            & (TaskModel.process_instance_id == process_instance_id),
        )
        .outerjoin(TaskDefinitionModel, TaskDefinitionModel.id == TaskModel.task_definition_id)
        .outerjoin(BpmnProcessModel, BpmnProcessModel.id == TaskModel.bpmn_process_id)
        .outerjoin(
            BpmnProcessDefinitionModel,
            BpmnProcessDefinitionModel.id == BpmnProcessModel.bpmn_process_definition_id,
        )
        .where(
            ProcessInstanceEventModel.process_instance_id == process_instance_id,
            ProcessInstanceEventModel.m8f_tenant_id == tenant_id,
        )
        .order_by(ProcessInstanceEventModel.timestamp, ProcessInstanceEventModel.id)
    )
    rows: list[dict[str, Any]] = []
    for (
        event,
        actor_display,
        actor_username,
        bpmn_process,
        task_name,
        task_identifier,
        task_type,
    ) in session.execute(stmt):
        rows.append(
            {
                "id": event.id,
                "bpmn_process": bpmn_process,
                "task_name": task_name,
                "task_identifier": task_identifier,
                "task_type": task_type,
                "event_type": event.event_type,
                "user": actor_display or actor_username or "system",
                "timestamp": float(event.timestamp) if event.timestamp is not None else None,
            }
        )
    return rows


def list_instance_milestones_for_designer(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> list[dict[str, Any]]:
    """Milestones tab: zero or one current row from ``last_milestone_bpmn_name``.
    Not a history. Timestamp is instance start (when the column is written).
    Bpmn process is the definition identifier, not the catalog path.
    """
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    instance = session.scalars(
        select(ProcessInstanceModel).where(
            ProcessInstanceModel.id == process_instance_id,
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
        )
    ).first()
    if instance is None:
        return []
    milestone = (instance.last_milestone_bpmn_name or "").strip()
    if not milestone:
        return []

    bpmn_process: str | None = None
    if instance.bpmn_process_definition_id is not None:
        definition = session.get(BpmnProcessDefinitionModel, instance.bpmn_process_definition_id)
        if definition is not None and definition.m8f_tenant_id == tenant_id:
            bpmn_process = definition.bpmn_identifier

    return [
        {
            "milestone": milestone,
            "bpmn_process": bpmn_process,
            "timestamp": instance.start_in_seconds,
        }
    ]


def list_pending_tasks_for_user(
    session: Session, *, tenant_id: str | None, user_id: int, limit: int = 10
) -> list[HumanTaskModel]:
    """Home "My tasks" support. Same assignment-exists-subquery filter as
    count_pending_tasks / GetPendingTasksQuery -- NOT a wrapper around
    list_pending_tasks_for_super_admin (that returns every pending task for
    every user). tenant_id=None means all tenants for this one user_id
    (caller-verified super-admin-only). Ordered oldest-first by id to match
    GetPendingTasksQuery's order_by(HumanTaskModel.id). Excludes tasks on
    suspended instances.
    """
    # tenant_id=None (all tenants) is caller-verified-super-admin-only --
    # see count_active_process_instances for why this isn't re-checked here.
    capped = max(1, min(int(limit), 50))
    stmt = (
        select(HumanTaskModel)
        .join(ProcessInstanceModel, ProcessInstanceModel.id == HumanTaskModel.process_instance_id)
        .where(
            HumanTaskModel.completed.is_(False),
            ProcessInstanceModel.status != ProcessInstanceStatus.suspended.value,
        )
    )
    exists_clause = select(1).where(
        HumanTaskUserModel.human_task_id == HumanTaskModel.id,
        HumanTaskUserModel.user_id == user_id,
    )
    if tenant_id is not None:
        stmt = stmt.where(HumanTaskModel.m8f_tenant_id == tenant_id)
        exists_clause = exists_clause.where(HumanTaskUserModel.m8f_tenant_id == tenant_id)
    stmt = stmt.where(exists(exists_clause)).order_by(HumanTaskModel.id).limit(capped)
    return list(session.scalars(stmt))


def list_completable_tasks_for_designer(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    user_id: int,
) -> list[dict[str, Any]]:
    """Tasks I can complete: incomplete human tasks on this instance where
    ``user_id`` is a candidate. Not ``list_human_tasks_for_instance`` (that
    is the approval chain: owner ``name``, every task). Same
    assignment-exists filter as ``list_pending_tasks_for_user``, plus
    ``process_instance_id``. Oldest-first. Empty when the instance is
    suspended — those tasks are not completable until resume.
    """
    instance = session.scalars(
        select(ProcessInstanceModel).where(
            ProcessInstanceModel.id == process_instance_id,
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
        )
    ).first()
    if instance is not None and instance.status == ProcessInstanceStatus.suspended.value:
        return []

    exists_clause = select(1).where(
        HumanTaskUserModel.human_task_id == HumanTaskModel.id,
        HumanTaskUserModel.user_id == user_id,
        HumanTaskUserModel.m8f_tenant_id == tenant_id,
    )
    stmt = (
        select(HumanTaskModel)
        .where(
            HumanTaskModel.m8f_tenant_id == tenant_id,
            HumanTaskModel.process_instance_id == process_instance_id,
            HumanTaskModel.completed.is_(False),
            exists(exists_clause),
        )
        .order_by(HumanTaskModel.created_at_in_seconds, HumanTaskModel.id)
    )
    return [
        {
            "id": task.id,
            "task_title": task.task_title,
            "task_name": task.task_name,
            "lane_name": task.lane_name,
        }
        for task in session.scalars(stmt)
    ]


def list_completed_tasks_for_designer(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    user_id: int,
) -> dict[str, list[dict[str, Any]]]:
    """Tasks tab: completed human tasks on this instance. Not
    ``list_human_tasks_for_instance`` (that is the approval chain: owner
    ``name``, every task). Task is title + name; Completed by is the
    completer person (display_name or username), never the owner ``name``.
    ``completed_by_me`` is ``completed_by_user_id == user_id``. Oldest-first
    by ``updated_at_in_seconds``, then id. Timestamp is that updated stamp.
    """
    from sqlalchemy.orm import aliased

    from m8flow_bpmn_core.models.user import UserModel

    completer = aliased(UserModel)
    stmt = (
        select(HumanTaskModel, completer.display_name, completer.username)
        .outerjoin(completer, completer.id == HumanTaskModel.completed_by_user_id)
        .where(
            HumanTaskModel.m8f_tenant_id == tenant_id,
            HumanTaskModel.process_instance_id == process_instance_id,
            HumanTaskModel.completed.is_(True),
        )
        .order_by(HumanTaskModel.updated_at_in_seconds, HumanTaskModel.id)
    )
    all_completed: list[dict[str, Any]] = []
    completed_by_me: list[dict[str, Any]] = []
    for task, completer_display, completer_username in session.execute(stmt):
        row = {
            "id": task.id,
            "task_title": task.task_title,
            "task_name": task.task_name,
            "completed_by": completer_display or completer_username,
            "timestamp": task.updated_at_in_seconds,
        }
        all_completed.append(row)
        if task.completed_by_user_id == user_id:
            completed_by_me.append(row)
    return {"completed_by_me": completed_by_me, "all_completed": all_completed}


def count_pending_tasks(session: Session, *, tenant_id: str | None, user_id: int) -> int:
    """Home-stats support ("tasks waiting on me"). NOT a len() wrapper
    around list_pending_tasks_for_super_admin -- that function returns
    every pending task for every user system-wide (no user_id param at
    all), which is the wrong shape for a "waiting on ME" stat. This
    duplicates GetPendingTasksQuery's own assignment-exists-subquery
    filter (m8flow_bpmn_core services/tasks.py get_pending_tasks) directly,
    just with the tenant_id condition made optional (both on the outer
    query and inside the exists-subquery) so tenant_id=None still means
    "all tenants" while staying scoped to this one user_id.
    tenant_id=None is caller-verified-super-admin-only, same as the
    process-instance stats above. Excludes tasks on suspended instances.
    """
    stmt = (
        select(func.count())
        .select_from(HumanTaskModel)
        .join(ProcessInstanceModel, ProcessInstanceModel.id == HumanTaskModel.process_instance_id)
        .where(
            HumanTaskModel.completed.is_(False),
            ProcessInstanceModel.status != ProcessInstanceStatus.suspended.value,
        )
    )
    exists_clause = select(1).where(
        HumanTaskUserModel.human_task_id == HumanTaskModel.id,
        HumanTaskUserModel.user_id == user_id,
    )
    if tenant_id is not None:
        stmt = stmt.where(HumanTaskModel.m8f_tenant_id == tenant_id)
        exists_clause = exists_clause.where(HumanTaskUserModel.m8f_tenant_id == tenant_id)
    stmt = stmt.where(exists(exists_clause))
    return int(session.scalar(stmt) or 0)


def run_due(
    session: Session,
    *,
    now_in_seconds: int | None = None,
    limit: int = 100,
    worker_id: str = "inline",
    tenant_id: str | None = None,
) -> int:
    """Poll due scheduler jobs. The timer-start, intermediate-timer, and
    process-retry job paths handled here call into m8flow_bpmn_core
    (services/workflow_runtime.py) with autonomous_failure_state_persistence
    enabled: on a ServiceTaskExecutionError, core opens its own
    `autonomous_session = Session(bind=engine, ...)` bound to the same
    engine as the session passed in here and commits the process instance's
    error/recovery state on that independent session, regardless of what
    happens to `session` afterward. CompleteTaskCommand does not use this
    mechanism. Callers of run_due don't need extra commit/session handling
    for that recovery state -- core already commits it internally for the
    job types processed here.
    """
    try:
        return api.run_due_scheduler_jobs(
            session,
            now_in_seconds=now_in_seconds,
            limit=limit,
            worker_id=worker_id,
            tenant_id=tenant_id,
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc


def _latest_definition_id(
    session: Session, *, tenant_id: str, process_model_identifier: str
) -> int:
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    version = session.scalars(
        select(ProcessModelBpmnVersionModel)
        .where(
            ProcessModelBpmnVersionModel.m8f_tenant_id == tenant_id,
            ProcessModelBpmnVersionModel.process_model_identifier == process_model_identifier,
        )
        .order_by(ProcessModelBpmnVersionModel.created_at_in_seconds.desc())
        .limit(1)
    ).first()
    if version is None:
        raise ApiError(
            "not_found",
            f"No imported definition for process model {process_model_identifier}",
            404,
        )
    definitions = session.scalars(
        select(BpmnProcessDefinitionModel)
        .where(BpmnProcessDefinitionModel.m8f_tenant_id == tenant_id)
        .order_by(BpmnProcessDefinitionModel.id.desc())
    ).all()
    for definition in definitions:
        if definition.process_model_identifier == process_model_identifier:
            return definition.id
    hashed = session.scalars(
        select(BpmnProcessDefinitionModel).where(
            BpmnProcessDefinitionModel.m8f_tenant_id == tenant_id,
            BpmnProcessDefinitionModel.full_process_model_hash == version.bpmn_xml_hash,
        )
    ).first()
    if hashed is not None:
        return hashed.id
    raise ApiError(
        "not_found",
        f"No bpmn_process_definition for {process_model_identifier}",
        404,
    )


def _stringify_metadata_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value)
