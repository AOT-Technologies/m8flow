from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, exists, func, or_, select, text
from sqlalchemy.orm import Session

from m8flow_bpmn_core import api
from m8flow_bpmn_core.errors import BpmnCoreError, InvalidStateError
from m8flow_bpmn_core.models.human_task import HumanTaskModel
from m8flow_bpmn_core.models.human_task_user import HumanTaskUserModel
from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel, ProcessInstanceStatus
from m8flow_bpmn_core.models.process_instance_metadata import ProcessInstanceMetadataModel
from m8flow_bpmn_core.models.work_item import WorkItemModel
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


def _iso_datetime(value: datetime | None) -> str | None:
    """Serialize a core timestamp as an explicit UTC ISO-8601 value."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _iso_epoch(seconds: float | None) -> str | None:
    """Serialize an epoch-seconds stamp (e.g. Spiff ``last_state_change``) like ``_iso_datetime``."""
    return _iso_datetime(datetime.fromtimestamp(seconds, timezone.utc)) if seconds is not None else None


def _event_category(event: Any) -> str | None:
    """Return the persisted category, deriving it for pre-category rows."""
    category = getattr(event, "category", None)
    if category is not None:
        return str(getattr(category, "value", category))
    return _category_for_event_type(event.event_type)


def _category_for_event_type(event_type: str) -> str | None:
    from m8flow_bpmn_core.models.process_instance_event import event_category_for_type

    try:
        return event_category_for_type(event_type).value
    except ValueError:
        # Preserve the event row for compatibility if an older/custom event
        # value cannot be classified by the core enum.
        return None


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
    start = instance.started_at
    end = instance.ended_at or datetime.now(timezone.utc)
    duration_seconds = None
    if start is not None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        duration_seconds = max(0.0, (end - start).total_seconds())
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


# Flag ExternalFormService.submit() sets on the request so that the external-form
# submission is the ONLY path allowed to complete a user task carrying externalFormUrl.
EXTERNAL_FORM_COMPLETION_FLAG = "_m8flow_external_form_completion"


def _reject_in_app_completion_of_external_form_task(
    session: Session, *, tenant_id: str, human_task_id: int
) -> None:
    """Host guard: a task whose modeler marked it `externalFormUrl` is completed by its
    recipient through the emailed secure link, and by nothing else.

    Without this, the in-app task page (or any other caller of `complete`) could finish
    the task on the recipient's behalf, which defeats the point of issuing a per-recipient
    link and silently strands the tracking row. The external path is recognised by the
    flag `ExternalFormService.submit` sets on the request; a caller with no request
    context is never that path.

    Fails open on an unreadable task definition: a lookup problem must not block ordinary
    task completion, and a task with no readable extensions has no externalFormUrl to
    enforce anyway.
    """
    from flask import g, has_request_context

    if has_request_context() and bool(getattr(g, EXTERNAL_FORM_COMPLETION_FLAG, False)):
        return

    task = session.get(HumanTaskModel, human_task_id)
    if task is None or task.m8f_tenant_id != tenant_id:
        return
    try:
        from m8flow_backend.services.external_form_service import external_form_url_for_task

        is_external_form = bool(external_form_url_for_task(task))
    except Exception:
        LOGGER.warning(
            "external-form guard: could not inspect human task %s; allowing completion",
            human_task_id,
            exc_info=True,
        )
        return

    if is_external_form:
        LOGGER.info(
            "external-form guard: blocked in-app completion of external-form task %s",
            human_task_id,
        )
        raise ApiError(
            "external_form_task_not_completable_in_app",
            (
                "This task is completed through its external form and cannot be completed here."
                " It stays open until the recipient submits the secure link."
            ),
            409,
        )


def _acting_tenant_membership(session: Session, *, tenant_id: str, user_id: int):
    """Scope a super-admin into `tenant_id` for the duration of one core command.

    m8flow-bpmn-core guards every write command with
    `ensure_user_belongs_to_tenant`, which sits above core's
    authorization-policy seam and so is unreachable by
    `HostAuthorizationPolicy` (that seam already allows super-admins for the
    RBAC guard immediately after). Without this, a super-admin acting in a
    tenant they did not log into gets "User N does not belong to tenant X".

    A no-op for everyone else -- see
    `identity.super_admin_tenant_membership` for why nothing is persisted.
    """
    from m8flow_backend.identity import super_admin_tenant_membership
    from m8flow_bpmn_core.models.user import UserModel

    return super_admin_tenant_membership(
        session, user=session.get(UserModel, user_id), tenant_id=tenant_id
    )


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
        with _acting_tenant_membership(session, tenant_id=tenant_id, user_id=user_id):
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


def _require_startable_status(*, tenant_id: str, process_model_identifier: str) -> None:
    """Only published models start instances (M8F-508).

    Guarding here rather than in the route means the designer Start button,
    the thin POST /v1.0/process-instances, and MCP all hit the same rule.
    `catalog` imports this module, so the import is deferred to the call to
    keep the cycle from closing at import time.
    """
    from m8flow_backend import catalog

    status = catalog.process_model_status(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    if status not in catalog.PROCESS_MODEL_STARTABLE_STATUSES:
        raise ApiError(
            "process_model_not_startable",
            f"Process model is {status} and cannot be started. Publish it first.",
            409,
        )


def _emit_external_form_requests(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> None:
    """Notify recipients of any external-form task this write left ready.

    Best-effort: the notification path must never break the workflow write that
    triggered it. `services` imports this module, so the import is deferred to
    the call to keep the cycle from closing at import time.
    """
    try:
        from m8flow_backend.services.external_form_service import ExternalFormService

        ExternalFormService.emit_requests_for_ready_tasks(
            session, tenant_id=tenant_id, process_instance_id=process_instance_id
        )
    except Exception:
        LOGGER.warning(
            "external-form notification hook failed for process instance %s",
            process_instance_id,
            exc_info=True,
        )


def _model_display_name(*, tenant_id: str, process_model_identifier: str) -> str:
    """The process model's own display name (process_model.json), leaf id as fallback.

    Core names a new instance after the BPMN process element's ``name`` and falls
    back to the model *identifier* when the element is unnamed, so instances (and
    their human tasks) surfaced the id instead of the model's display name.
    Deferred import: ``catalog`` imports this module.
    """
    from m8flow_backend import catalog

    return catalog.process_model_display_name(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )


def _display_name_for_row(instance: ProcessInstanceModel, cache: dict[tuple[str, str], str]) -> str:
    """Read-time repair for rows stored before the start-time fix: an instance whose
    stored display name is just its model id reads the model's real display name."""
    stored = instance.process_model_display_name
    identifier = instance.process_model_identifier
    if stored and stored not in (identifier, identifier.rstrip("/").split("/")[-1]):
        return stored
    key = (instance.m8f_tenant_id, identifier)
    if key not in cache:
        try:
            cache[key] = _model_display_name(tenant_id=key[0], process_model_identifier=identifier)
        except Exception:  # noqa: BLE001 - display-only; never fail a read over it
            cache[key] = stored or identifier
    return cache[key]


def _apply_model_display_name(
    session: Session, instance: ProcessInstanceModel, *, tenant_id: str, process_model_identifier: str
) -> None:
    display_name = _model_display_name(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if not display_name or instance.process_model_display_name == display_name:
        return
    instance.process_model_display_name = display_name
    # Human tasks created during start copied the core default; keep them in step.
    for task in session.scalars(
        select(HumanTaskModel).where(
            HumanTaskModel.process_instance_id == instance.id,
            HumanTaskModel.m8f_tenant_id == tenant_id,
        )
    ):
        task.process_model_display_name = display_name
    session.flush()


def start(
    session: Session,
    *,
    tenant_id: str,
    user_id: int,
    process_model_identifier: str,
    summary: str | None = None,
    submission_metadata: dict[str, Any] | None = None,
) -> ProcessInstanceModel:
    """Start an instance of the model's BPMN as it is on disk.

    Transaction contract: Start is not atomic with the caller's transaction.
    Core creates the instance in its own session and commits it there. When the
    on-disk BPMN is not yet imported for this model, Start first imports it and
    COMMITS `session` (see `_definition_id_for_start`), so anything the caller
    staged before calling is committed too. Commit or discard your own writes
    before calling Start if they must roll back with a failed Start. The route
    callers stage nothing: auth commits its own user/group sync.
    """
    _require_startable_status(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    definition_id = _definition_id_for_start(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        process_model_identifier=process_model_identifier,
    )
    try:
        with _acting_tenant_membership(session, tenant_id=tenant_id, user_id=user_id):
            instance = api.execute_command(
                session,
                api.InitializeProcessInstanceFromDefinitionCommand(
                    tenant_id=tenant_id,
                    bpmn_process_definition_id=definition_id,
                    process_initiator_id=user_id,
                    summary=summary,
                    submission_metadata={
                        str(key): _stringify_metadata_value(value)
                        for key, value in (submission_metadata or {}).items()
                    }
                    or None,
                    started_at=datetime.now(timezone.utc),
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
    _apply_model_display_name(
        session, instance, tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    record_process_instance_created(tenant_id)
    record_process_instance_active_delta(tenant_id, 1)
    _emit_external_form_requests(session, tenant_id=tenant_id, process_instance_id=instance.id)
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


def reconcile_pending_tasks_for_user(
    session: Session,
    *,
    tenant_id: str,
    user_id: int,
) -> list[HumanTaskModel]:
    """Reconcile newly synchronized lane membership with pending tasks.

    The core service adds only potential-owner rows for pending tasks whose
    lane group contains the user. It is tenant-scoped and idempotent; claiming
    the task remains a separate operation and therefore ``actual_owner_id``
    stays unset until the user explicitly claims it.
    """
    try:
        return api.assign_pending_tasks_for_user(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
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
        payload = _nest_payload_under_task_variable(
            session,
            tenant_id=tenant_id,
            human_task_id=human_task_id,
            task_payload=task_payload,
        )
        payload = {str(key): _stringify_metadata_value(value) for key, value in payload.items()}
    try:
        _reject_task_write_if_instance_suspended(
            session, tenant_id=tenant_id, human_task_id=human_task_id, action="complete"
        )
        _reject_in_app_completion_of_external_form_task(
            session, tenant_id=tenant_id, human_task_id=human_task_id
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
        _emit_external_form_requests(
            session, tenant_id=tenant_id, process_instance_id=int(process_instance_id)
        )
    return instance


def _nest_payload_under_task_variable(
    session: Session,
    *,
    tenant_id: str,
    human_task_id: int,
    task_payload: dict[str, Any],
) -> dict[str, Any]:
    """Honor a user task's ``spiffworkflow:variableName``.

    A user task may declare ``<spiffworkflow:variableName>x</...>``, meaning
    "collect this form into ``x``" -- downstream tasks then read
    ``x.get("field")``. SpiffWorkflow parses it onto ``UserTask.variable`` and
    exposes ``add_data_from_form`` to apply it, but nothing in the host, core
    or SpiffWorkflow itself ever calls that method, so the nesting was silently
    dropped: core stores the form flat and re-applies it flat, leaving ``x`` at
    whatever an init script seeded it with. Nest here, at the one choke point
    every completion path already funnels through.

    The reserved ``outcome`` gateway variable stays top-level -- gateway
    conditions read it unqualified.
    """
    task = session.get(HumanTaskModel, human_task_id)
    if task is None or task.m8f_tenant_id != tenant_id:
        return dict(task_payload)
    variable = _user_task_form_variable(task)
    if not variable:
        return dict(task_payload)
    nested = {key: value for key, value in task_payload.items() if key != "outcome"}
    # Core applies the payload with a shallow update, so merge onto whatever
    # scripts/earlier steps already put under the variable instead of
    # replacing it wholesale.
    existing = _task_data(session, tenant_id=tenant_id, task_guid=task.task_guid).get(variable)
    base = existing if isinstance(existing, dict) else {}
    payload: dict[str, Any] = {variable: {**base, **nested}}
    if "outcome" in task_payload:
        payload["outcome"] = task_payload["outcome"]
    return payload


def _user_task_form_variable(task: HumanTaskModel) -> str | None:
    """Return the task spec's serialized ``variable``, if it declares one.

    ``variable`` is the serializer's name for ``spiffworkflow:variableName``
    (SpiffWorkflow/spiff/serializer/task_spec.py). It reaches us through the
    human task's ``json_metadata["task_definition_properties"]``.
    """
    metadata = task.json_metadata if isinstance(task.json_metadata, dict) else {}
    props = metadata.get("task_definition_properties")
    if not isinstance(props, dict):
        return None
    variable = props.get("variable")
    return variable.strip() if isinstance(variable, str) and variable.strip() else None


_TERMINAL_TASK_STATES = frozenset({"COMPLETED", "ERROR", "CANCELLED"})


def _last_state_change(properties_json: Any) -> float | None:
    """Spiff's own per-task state-change stamp. Use this, not
    ``TaskModel.ended_at``: core rewrites that on every persist."""
    value = properties_json.get("last_state_change") if isinstance(properties_json, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _task_data(session: Session, *, tenant_id: str, task_guid: str | None) -> dict[str, Any]:
    """Current task data (``TaskModel.json_data_hash -> JsonDataModel.data``), tenant-scoped."""
    if not task_guid:
        return {}

    from m8flow_bpmn_core.models.json_data import JsonDataModel
    from m8flow_bpmn_core.models.task import TaskModel

    task = session.scalars(
        select(TaskModel).where(
            TaskModel.guid == task_guid,
            TaskModel.m8f_tenant_id == tenant_id,
        )
    ).first()
    if task is None or not task.json_data_hash:
        return {}
    json_data = JsonDataModel.get_for_tenant(session, tenant_id, task.json_data_hash)
    if json_data is None or not isinstance(json_data.data, dict):
        return {}
    return json_data.data


def _process_data(session: Session, *, tenant_id: str, process_instance_id: int) -> dict[str, Any]:
    """Accumulated process variables for the instance, minus core's internal ``__m8f*``
    keys (e.g. the serialized workflow state). Core stores user-task submissions here,
    not on the task, so a task's own ``_task_data`` is usually ``{}``."""
    from m8flow_bpmn_core.models.json_data import JsonDataModel

    instance = session.get(ProcessInstanceModel, process_instance_id)
    if instance is None or instance.m8f_tenant_id != tenant_id:
        return {}
    data_hash = getattr(instance.bpmn_process, "json_data_hash", None)
    if not data_hash:
        return {}
    json_data = JsonDataModel.get_for_tenant(session, tenant_id, data_hash)
    if json_data is None or not isinstance(json_data.data, dict):
        return {}
    return {key: value for key, value in json_data.data.items() if not key.startswith("__m8f")}


_ERROR_MESSAGE_MAX_LENGTH = 4000


def record_service_task_error(*, context: Any, exc: BaseException) -> None:
    """Persist why a service task failed, on its own committed session: the
    request session that ran the task rolls back on the error response, and
    the scheduler swallows the exception into a batch error. Never raises --
    losing the message must not mask the original failure.

    Only a ``ServiceTaskExecutionError``'s text is meant for users (its
    registry wrappers mask secrets in it); any other exception may carry
    internals such as SQL, so only its type is kept.
    """
    if context is None or getattr(context, "process_instance_id", None) is None:
        return
    try:
        from m8flow_bpmn_core.errors import ServiceTaskExecutionError

        from m8flow_backend.db import session_scope
        from m8flow_backend.models.process_instance_error import ProcessInstanceErrorModel

        if isinstance(exc, ServiceTaskExecutionError):
            message = str(exc).strip() or type(exc).__name__
        else:
            message = f"Service task failed ({type(exc).__name__})"
        message = message[:_ERROR_MESSAGE_MAX_LENGTH]
        with session_scope() as session:
            session.add(
                ProcessInstanceErrorModel(
                    m8f_tenant_id=context.tenant_id,
                    process_instance_id=context.process_instance_id,
                    task_guid=context.task_guid,
                    message=message,
                    created_at_in_seconds=int(time.time()),
                )
            )
    except Exception:
        LOGGER.exception(
            "Failed to record service task error for process instance %s",
            context.process_instance_id,
        )


def list_instance_errors(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> list[tuple[str | None, str]]:
    """``(task_guid, message)`` per recorded service-task failure, oldest first
    (``dict(...)`` keeps the latest message per task)."""
    from m8flow_backend.models.process_instance_error import ProcessInstanceErrorModel

    return [
        (task_guid, message)
        for task_guid, message in session.execute(
            select(ProcessInstanceErrorModel.task_guid, ProcessInstanceErrorModel.message)
            .where(
                ProcessInstanceErrorModel.m8f_tenant_id == tenant_id,
                ProcessInstanceErrorModel.process_instance_id == process_instance_id,
            )
            .order_by(ProcessInstanceErrorModel.id)
        )
    ]


def suspend_instance(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    user_id: int,
) -> ProcessInstanceModel:
    try:
        with _acting_tenant_membership(session, tenant_id=tenant_id, user_id=user_id):
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
        with _acting_tenant_membership(session, tenant_id=tenant_id, user_id=user_id):
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
        with _acting_tenant_membership(session, tenant_id=tenant_id, user_id=user_id):
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


def delete_instance(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
) -> int:
    """Permanently delete one *finished* process instance and its run data.

    Only complete / terminated / error instances can be deleted; an active or
    suspended one must be terminated first (409 otherwise), so deletion never
    races a running workflow. Core has no delete command, so this removes the
    instance through the ORM: the ProcessInstanceModel relationships cascade
    to tasks, human tasks (and their potential owners), events, metadata and
    scheduler jobs. Host-side rows keyed only by ``process_instance_id`` (no
    FK) are removed explicitly. Shared rows -- the process definition, the
    ``bpmn_process`` it points at, content-addressed json data -- are kept.
    """
    from sqlalchemy import delete as sql_delete

    from m8flow_backend.models.external_form_request import ExternalFormRequestModel
    from m8flow_backend.models.native import (
        ProcessInstanceFileDataModel,
        TaskDraftDataModel,
        TaskInstructionsForEndUserModel,
    )

    instance = session.get(ProcessInstanceModel, process_instance_id)
    if instance is None or instance.m8f_tenant_id != tenant_id:
        raise ApiError("not_found", "Process instance not found", 404)
    if _instance_status_value(instance.status) not in _TERMINAL_INSTANCE_STATUSES:
        raise ApiError(
            "process_instance_not_finished",
            f"Process instance is {_instance_status_value(instance.status)}; "
            "only complete, terminated or error instances can be deleted. Terminate it first.",
            409,
        )
    for model in (
        TaskDraftDataModel,
        TaskInstructionsForEndUserModel,
        ProcessInstanceFileDataModel,
        ExternalFormRequestModel,
    ):
        session.execute(
            sql_delete(model).where(
                model.process_instance_id == process_instance_id,
                model.m8f_tenant_id == tenant_id,
            )
        )
    session.delete(instance)
    session.flush()
    LOGGER.info(
        "process_instance.deleted tenant_id=%s process_instance_id=%s",
        tenant_id,
        process_instance_id,
    )
    return process_instance_id


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
    """Return pending tasks using normalized claim state.

    Core's public pending-task query remains legacy-model-shaped for API
    compatibility. The host inbox uses the normalized work-item state while
    retaining a fallback for rows awaiting backfill.
    """
    pending_state = or_(
        WorkItemModel.completed.is_(False),
        WorkItemModel.id.is_(None) & HumanTaskModel.completed.is_(False),
    )
    assignment = exists(
        select(1).where(
            HumanTaskUserModel.human_task_id == HumanTaskModel.id,
            HumanTaskUserModel.user_id == user_id,
            HumanTaskUserModel.m8f_tenant_id == tenant_id,
        )
    )
    stmt = (
        select(HumanTaskModel)
        .join(ProcessInstanceModel, ProcessInstanceModel.id == HumanTaskModel.process_instance_id)
        .outerjoin(WorkItemModel, WorkItemModel.id == HumanTaskModel.id)
        .where(
            HumanTaskModel.m8f_tenant_id == tenant_id,
            pending_state,
            assignment,
            ProcessInstanceModel.status != ProcessInstanceStatus.suspended.value,
        )
        .order_by(HumanTaskModel.id)
    )
    return list(session.scalars(stmt))


def list_pending_tasks_for_super_admin(session: Session) -> list[HumanTaskModel]:
    if not is_super_admin_request():
        raise ApiError("permission_denied", "Super-admin access required", 403)
    pending_state = or_(
        WorkItemModel.completed.is_(False),
        WorkItemModel.id.is_(None) & HumanTaskModel.completed.is_(False),
    )
    return list(
        session.scalars(
            select(HumanTaskModel)
            .join(ProcessInstanceModel, ProcessInstanceModel.id == HumanTaskModel.process_instance_id)
            .outerjoin(WorkItemModel, WorkItemModel.id == HumanTaskModel.id)
            .where(
                pending_state,
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
    start_of_day = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.count())
        .select_from(ProcessInstanceModel)
        .where(
            ProcessInstanceModel.status == ProcessInstanceStatus.complete,
            ProcessInstanceModel.ended_at.is_not(None),
            ProcessInstanceModel.ended_at >= start_of_day,
        )
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    return int(session.scalar(stmt) or 0)


def average_completion_minutes(session: Session, *, tenant_id: str | None = None) -> float | None:
    """Home-stats support. Average over ALL completed instances (not scoped
    to "today" -- that's count_process_instances_completed_today), using
    started_at -> ended_at. started_at is populated once
    the instance actually starts running (m8flow_bpmn_core's
    workflow_runtime.py), not at creation. Returns None (not 0) when there
    are no completed instances yet, so the caller can distinguish "no data"
    from "instantly complete".
    """
    # tenant_id=None (all tenants) is caller-verified-super-admin-only --
    # see count_active_process_instances for why this isn't re-checked here.
    stmt = select(ProcessInstanceModel.started_at, ProcessInstanceModel.ended_at).where(
        ProcessInstanceModel.status == ProcessInstanceStatus.complete,
        ProcessInstanceModel.started_at.is_not(None),
        ProcessInstanceModel.ended_at.is_not(None),
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    durations = []
    for started_at, ended_at in session.execute(stmt):
        if started_at is not None and ended_at is not None:
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            if ended_at.tzinfo is None:
                ended_at = ended_at.replace(tzinfo=timezone.utc)
            durations.append(max(0.0, (ended_at - started_at).total_seconds()))
    if not durations:
        return None
    return round(sum(durations) / len(durations) / 60, 1)


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
    session: Session, *, tenant_id: str | None
) -> dict[tuple[str, str], dict[str, int | None]]:
    """Per-process-model last_run_at + runs_30d for the Processes list.

    Keyed by ``(tenant_id, process_model_identifier)``, never by the bare
    identifier: model identifiers are catalog paths and DO collide across
    tenants, so grouping on the identifier alone would silently merge two
    tenants' stats into one row on an all-tenants read.

    ``tenant_id`` None means "all tenants" (caller-verified super-admin only).
    runs_30d counts instances whose started_at falls in the last 30 days
    (null starts excluded); last_run_at is max(started_at).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    runs_30d_expr = func.coalesce(
        func.sum(
            case(
                (
                    (ProcessInstanceModel.started_at.is_not(None))
                    & (ProcessInstanceModel.started_at >= cutoff),
                    1,
                ),
                else_=0,
            )
        ),
        0,
    )
    stmt = select(
        ProcessInstanceModel.m8f_tenant_id,
        ProcessInstanceModel.process_model_identifier,
        func.max(ProcessInstanceModel.started_at),
        runs_30d_expr,
    ).group_by(
        ProcessInstanceModel.m8f_tenant_id,
        ProcessInstanceModel.process_model_identifier,
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    out: dict[tuple[str, str], dict[str, int | None]] = {}
    for row_tenant_id, model_id, last_run, runs_30d in session.execute(stmt):
        out[(str(row_tenant_id), str(model_id))] = {
            "last_run_at": _iso_datetime(last_run),
            "runs_30d": int(runs_30d or 0),
        }
    return out


def process_model_detail_stats(
    session: Session, *, tenant_id: str, process_model_identifier: str
) -> dict[str, int | None]:
    """Key numbers for one process model: last_run, running_now, runs_30d."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    active = ProcessInstanceModel.active_statuses()
    last_run = session.scalar(
        select(func.max(ProcessInstanceModel.started_at)).where(
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
            ProcessInstanceModel.started_at.is_not(None),
            ProcessInstanceModel.started_at >= cutoff,
        )
    )
    return {
        "last_run_at": _iso_datetime(last_run),
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
        if instance.started_at is not None and instance.ended_at is not None:
            duration = int((instance.ended_at - instance.started_at).total_seconds())
        rows.append(
            {
                "id": instance.id,
                "started_by": username or "",
                "started_at": _iso_datetime(instance.started_at),
                "duration_seconds": duration,
                "status": instance.status,
            }
        )
    return rows


def list_instances_for_designer(
    session: Session,
    *,
    tenant_id: str | None,
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
        )
        # tenant_id None == "all tenants": caller-verified super-admin only
        # (auth.resolve_read_tenant_id). Same posture as
        # count_active_process_instances above.
        if tenant_id is not None:
            stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
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
    display_names: dict[tuple[str, str], str] = {}
    for instance, username in session.execute(stmt):
        rows.append(
            {
                "id": instance.id,
                "tenant_id": instance.m8f_tenant_id,
                "process_model_identifier": instance.process_model_identifier,
                "process_model_display_name": _display_name_for_row(instance, display_names),
                "status": instance.status,
                "started_by": username or "",
                "started_at": _iso_datetime(instance.started_at),
                "ended_at": _iso_datetime(instance.ended_at),
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
        ProcessInstanceModel.started_at.desc().nullslast(),
        ProcessInstanceModel.id.desc(),
    ),
    "status": lambda: (
        ProcessInstanceModel.status.asc(),
        ProcessInstanceModel.id.desc(),
    ),
}


def list_instance_owners_for_designer(
    session: Session, *, tenant_id: str | None
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
        .where(UserModel.username.isnot(None))
        .distinct()
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    # Sort in Python: Postgres rejects DISTINCT + ORDER BY lower(username)
    # unless lower(username) is also in the select list. SQLite allowed it,
    # so unit tests didn't catch the 500 on GET .../process-instances/owners.
    return sorted(
        (username for (username,) in session.execute(stmt) if username),
        key=str.lower,
    )


def list_instance_owner_options_for_designer(
    session: Session, *, tenant_id: str | None
) -> list[dict[str, int | str]]:
    """Return stable local user ids and display usernames for owner filters.

    Usernames are display values only: they are not unique across identity
    sources. The local ``UserModel.id`` is the stable key used by the process
    model owner filter, and process-instance rows are still constrained by
    ``tenant_id`` when a concrete tenant is selected.
    """
    from m8flow_bpmn_core.models.user import UserModel

    stmt = (
        select(UserModel.id, UserModel.username)
        .join(
            ProcessInstanceModel,
            ProcessInstanceModel.process_initiator_id == UserModel.id,
        )
        .where(UserModel.username.isnot(None))
        .distinct()
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    return [
        {"id": int(user_id), "username": username}
        for user_id, username in sorted(
            session.execute(stmt),
            key=lambda row: (str(row[1]).casefold(), int(row[0])),
        )
        if username
    ]


def list_process_model_keys_for_instance_owner(
    session: Session, *, tenant_id: str | None, owner_id: int
) -> set[tuple[str, str]]:
    """Return model keys started by the stable local user ``owner_id``.

    The Processes page stores models on disk, while ownership is recorded on
    process-instance rows. This query keeps the owner filter tenant-scoped and
    works for the super-admin's all-tenant view without matching on a
    potentially duplicated username.
    """
    from m8flow_bpmn_core.models.user import UserModel

    stmt = (
        select(ProcessInstanceModel.m8f_tenant_id, ProcessInstanceModel.process_model_identifier)
        .join(UserModel, UserModel.id == ProcessInstanceModel.process_initiator_id)
        .where(UserModel.id == owner_id)
        .distinct()
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    return {
        (str(row_tenant_id), str(model_id))
        for row_tenant_id, model_id in session.execute(stmt)
    }


def get_instance_detail_for_designer(
    session: Session, *, tenant_id: str | None, process_instance_id: int, to_task_guid: str | None = None
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

    `to_task_guid` keeps only tasks that finished at or before that task
    (Spiff `last_state_change`); ApiError 404 if unknown, 400 unless it is
    COMPLETED/ERROR. `error_message` is the latest recorded failure message,
    set only while the instance status is "error".
    """
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel
    from m8flow_bpmn_core.models.user import UserModel

    # tenant_id None == "all tenants": caller-verified super-admin only
    # (auth.resolve_read_tenant_id).
    stmt = (
        select(ProcessInstanceModel, UserModel.username)
        .outerjoin(UserModel, UserModel.id == ProcessInstanceModel.process_initiator_id)
        .where(ProcessInstanceModel.id == process_instance_id)
    )
    if tenant_id is not None:
        stmt = stmt.where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
    row = session.execute(stmt).first()
    if row is None:
        return None
    instance, username = row

    # The definition and task lookups below are re-keyed onto the instance's own
    # tenant when tenant_id is None -- never left unfiltered. An all-tenants read
    # still reads one instance's data, not a cross-tenant union.
    scope_tenant_id = tenant_id if tenant_id is not None else instance.m8f_tenant_id

    bpmn_xml: str | None = None
    if instance.bpmn_process_definition_id is not None:
        definition = session.get(BpmnProcessDefinitionModel, instance.bpmn_process_definition_id)
        if definition is not None and definition.m8f_tenant_id == scope_tenant_id:
            bpmn_xml = definition.source_bpmn_xml

    task_rows = session.execute(
        select(
            TaskModel.guid,
            TaskDefinitionModel.bpmn_identifier,
            TaskDefinitionModel.bpmn_name,
            TaskDefinitionModel.typename,
            TaskModel.state,
            TaskModel.properties_json,
        )
        .join(TaskDefinitionModel, TaskDefinitionModel.id == TaskModel.task_definition_id)
        .where(
            TaskModel.process_instance_id == process_instance_id,
            TaskModel.m8f_tenant_id == scope_tenant_id,
        )
    ).all()
    tasks = [
        {
            "guid": guid,
            "bpmn_identifier": bpmn_identifier,
            "bpmn_name": bpmn_name,
            "typename": typename,
            "state": state,
            "last_state_change": _last_state_change(properties_json),
        }
        for guid, bpmn_identifier, bpmn_name, typename, state, properties_json in task_rows
    ]

    if to_task_guid is not None:
        # "As of this task": only tasks that had finished by the time it did
        # (legacy parity -- READY-at-the-time tasks aren't reconstructable).
        target = next((t for t in tasks if t["guid"] == to_task_guid), None)
        if target is None:
            raise ApiError("not_found", "Task not found for this process instance", 404)
        cutoff = target["last_state_change"]
        if target["state"] not in {"COMPLETED", "ERROR"} or cutoff is None:
            raise ApiError(
                "task_cannot_be_viewed_at",
                "Only completed or failed tasks can be viewed at a point in time",
                400,
            )
        tasks = [
            t
            for t in tasks
            if t["state"] in _TERMINAL_TASK_STATES
            and t["last_state_change"] is not None
            and t["last_state_change"] <= cutoff
        ]

    error_message = None
    if instance.status == ProcessInstanceStatus.error.value:
        errors = list_instance_errors(
            session, tenant_id=scope_tenant_id, process_instance_id=process_instance_id
        )
        error_message = errors[-1][1] if errors else None

    return {
        "id": instance.id,
        "tenant_id": instance.m8f_tenant_id,
        "process_model_identifier": instance.process_model_identifier,
        "process_model_display_name": _display_name_for_row(instance, {}),
        "status": instance.status,
        "started_by": username or "",
        "started_at": _iso_datetime(instance.started_at),
        "ended_at": _iso_datetime(instance.ended_at),
        "updated_at": _iso_datetime(instance.updated_at),
        "last_milestone_bpmn_name": instance.last_milestone_bpmn_name,
        "bpmn_xml": bpmn_xml,
        "tasks": tasks,
        "error_message": error_message,
    }


def get_instance_task_for_designer(
    session: Session, *, tenant_id: str, process_instance_id: int, task_guid: str
) -> dict[str, Any] | None:
    """One runtime task of an instance plus its current data, for the diagram
    task modal. None unless the task belongs to this instance and tenant."""
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel

    row = session.execute(
        select(
            TaskModel,
            TaskDefinitionModel.bpmn_identifier,
            TaskDefinitionModel.bpmn_name,
            TaskDefinitionModel.typename,
        )
        .join(TaskDefinitionModel, TaskDefinitionModel.id == TaskModel.task_definition_id)
        .where(
            TaskModel.guid == task_guid,
            TaskModel.process_instance_id == process_instance_id,
            TaskModel.m8f_tenant_id == tenant_id,
        )
    ).first()
    if row is None:
        return None
    task, bpmn_identifier, bpmn_name, typename = row
    return {
        "guid": task.guid,
        "bpmn_identifier": bpmn_identifier,
        "bpmn_name": bpmn_name,
        "typename": typename,
        "state": task.state,
        "last_state_change": _last_state_change(task.properties_json),
        # ponytail: falls back to the instance's current variables (core keeps no
        # per-task snapshot), so a past task shows today's values, not its own.
        "data": _task_data(session, tenant_id=tenant_id, task_guid=task.guid)
        or _process_data(session, tenant_id=tenant_id, process_instance_id=process_instance_id),
    }


def list_human_tasks_for_instance(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> list[dict[str, Any]]:
    """Approval chain for a process instance: every human task (completed +
    current), oldest-first. Raw ORM read -- m8flow_bpmn_core exposes no query
    for this shape (its own catalog only returns pending tasks or a bare
    instance row), so this mirrors get_instance_detail_for_designer's
    direct-select + UserModel-join posture.

    The normalized ``work_item`` row is the source of claim/completion state;
    the legacy ``human_task`` row remains the source of display metadata. A
    legacy fallback is retained for tasks awaiting backfill. `actual_owner_id`
    and `completed_by_user_id` are bare FK columns (no ORM relationships), so
    UserModel is outer-joined twice under aliases. `name`
    resolves the owner's display name (falling back to the completer's); it is
    None for a system-inactivated task (completed with no human completer and
    no owner). Ordered by `created_at, id` (id is the stable
    tiebreaker -- there is no BPMN step number). `completed_at` is
    `updated_at` for completed rows (core stamps it at completion),
    None while the task is still current. The normalized work-item timestamp
    is used when available.
    """
    from sqlalchemy.orm import aliased

    from m8flow_bpmn_core.models.user import UserModel

    owner = aliased(UserModel)
    completer = aliased(UserModel)
    stmt = (
        select(
            HumanTaskModel,
            WorkItemModel,
            owner.display_name,
            owner.username,
            completer.display_name,
            completer.username,
        )
        .outerjoin(WorkItemModel, WorkItemModel.id == HumanTaskModel.id)
        .outerjoin(
            owner,
            owner.id == func.coalesce(WorkItemModel.actual_owner_id, HumanTaskModel.actual_owner_id),
        )
        .outerjoin(
            completer,
            completer.id
            == func.coalesce(WorkItemModel.completed_by_user_id, HumanTaskModel.completed_by_user_id),
        )
        .where(
            HumanTaskModel.process_instance_id == process_instance_id,
            HumanTaskModel.m8f_tenant_id == tenant_id,
        )
        .order_by(
            func.coalesce(WorkItemModel.created_at, HumanTaskModel.created_at),
            HumanTaskModel.id,
        )
    )
    rows: list[dict[str, Any]] = []
    for (
        human_task,
        work_item,
        owner_display,
        owner_username,
        completer_display,
        completer_username,
    ) in (
        session.execute(stmt)
    ):
        owner_name = owner_display or owner_username
        completer_name = completer_display or completer_username
        completed = work_item.completed if work_item is not None else human_task.completed
        task_status = work_item.task_status if work_item is not None else human_task.task_status
        updated_at = (
            work_item.updated_at or human_task.updated_at
            if work_item is not None
            else human_task.updated_at
        )
        rows.append(
            {
                "name": owner_name or completer_name,
                "status": task_status,
                "completed": completed,
                "is_current": not completed,
                "lane_name": human_task.lane_name,
                "completed_at": _iso_datetime(updated_at) if completed else None,
            }
        )
    return rows


def list_instance_events(
    session: Session, *, tenant_id: str, process_instance_id: int
) -> list[dict[str, Any]]:
    """Activity feed for a process instance: the real, ordered event log
    (`ProcessInstanceEventModel`), oldest-first. Uses core's native
    `occurred_at` timestamp for ordering and response serialization.

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
        .order_by(ProcessInstanceEventModel.occurred_at, ProcessInstanceEventModel.id)
    )
    rows: list[dict[str, Any]] = []
    for event, actor_display, actor_username, task_title in session.execute(stmt):
        rows.append(
            {
                "event_type": event.event_type,
                "category": _event_category(event),
                "actor_name": actor_display or actor_username,
                "occurred_at": _iso_datetime(event.occurred_at),
                "task_guid": event.task_guid,
                "task_title": task_title,
            }
        )
    return rows


# Spiff's own bookkeeping tasks (workflow/subprocess root Start and End, the
# end join, and SpiffWorkflow 3.x's boundary/start-event split+join specs) --
# not BPMN elements, never shown as events.
_SPIFF_INTERNAL_TASK_TYPES = frozenset(
    {
        "BpmnStartTask",
        "SimpleBpmnTask",
        "_EndJoin",
        "BoundaryEventSplit",
        "BoundaryEventJoin",
        "StartEventSplit",
        "StartEventJoin",
    }
)
_TASK_EVENT_BY_STATE = {"COMPLETED": "task_completed", "ERROR": "task_failed", "CANCELLED": "task_cancelled"}


def list_instance_events_for_designer(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    event_type: str | None = None,
    task_type: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Events tab for process instance detail, oldest-first.

    Core's event log only records instance lifecycle, human-task completion and
    service-task failure, so every other BPMN task (script, service, start/end
    events, gateways) is synthesized from its terminal ``task`` row, stamped
    with Spiff's ``last_state_change`` (``id`` None). A task that already has a
    real event of the same type is not duplicated. Failed rows carry the
    host-recorded service-task error text. ``filter_options`` describe the
    unfiltered log. Task Review keeps the slim ``list_instance_events``.
    """
    from m8flow_bpmn_core.models.bpmn_process import BpmnProcessModel
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.process_instance_event import ProcessInstanceEventModel
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel
    from m8flow_bpmn_core.models.user import UserModel

    task_columns = (
        BpmnProcessDefinitionModel.bpmn_identifier,
        TaskDefinitionModel.bpmn_name,
        TaskDefinitionModel.bpmn_identifier,
        TaskDefinitionModel.typename,
    )
    event_stmt = (
        select(ProcessInstanceEventModel, UserModel.display_name, UserModel.username, *task_columns)
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
    )
    task_stmt = (
        select(TaskModel, *task_columns)
        .join(TaskDefinitionModel, TaskDefinitionModel.id == TaskModel.task_definition_id)
        .outerjoin(BpmnProcessModel, BpmnProcessModel.id == TaskModel.bpmn_process_id)
        .outerjoin(
            BpmnProcessDefinitionModel,
            BpmnProcessDefinitionModel.id == BpmnProcessModel.bpmn_process_definition_id,
        )
        .where(
            TaskModel.process_instance_id == process_instance_id,
            TaskModel.m8f_tenant_id == tenant_id,
            TaskModel.state.in_(tuple(_TASK_EVENT_BY_STATE)),
            TaskDefinitionModel.typename.notin_(_SPIFF_INTERNAL_TASK_TYPES),
        )
    )

    errors = list_instance_errors(session, tenant_id=tenant_id, process_instance_id=process_instance_id)
    error_by_guid = dict(errors)
    latest_error = errors[-1][1] if errors else None

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str]] = set()
    for event, actor_display, actor_username, bpmn_process, task_name, task_identifier, task_type_ in (
        session.execute(event_stmt)
    ):
        seen.add((event.task_guid, event.event_type))
        rows.append(
            {
                "id": event.id,
                "task_guid": event.task_guid,
                "bpmn_process": bpmn_process,
                "task_name": task_name,
                "task_identifier": task_identifier,
                "task_type": task_type_,
                "event_type": event.event_type,
                "category": _event_category(event),
                "user": actor_display or actor_username or "system",
                "occurred_at": _iso_datetime(event.occurred_at),
            }
        )
    for task, bpmn_process, task_name, task_identifier, task_type_ in session.execute(task_stmt):
        synthesized_type = _TASK_EVENT_BY_STATE[task.state]
        if (task.guid, synthesized_type) in seen:
            continue
        rows.append(
            {
                "id": None,
                "task_guid": task.guid,
                "bpmn_process": bpmn_process,
                "task_name": task_name,
                "task_identifier": task_identifier,
                "task_type": task_type_,
                "event_type": synthesized_type,
                "category": _category_for_event_type(synthesized_type),
                "user": "system",
                "occurred_at": _iso_epoch(_last_state_change(task.properties_json)),
            }
        )

    for row in rows:
        if row["event_type"] == "task_failed":
            row["error_message"] = error_by_guid.get(row["task_guid"])
        elif row["event_type"] == "process_instance_error":
            row["error_message"] = latest_error
        else:
            row["error_message"] = None

    # ponytail: merge/filter/paginate in Python -- fine for hundreds of tasks per
    # instance; push into a SQL UNION ALL with LIMIT/OFFSET if instances get huge.
    rows.sort(
        key=lambda r: (
            r["occurred_at"] is None,
            datetime.fromisoformat(r["occurred_at"]) if r["occurred_at"] else datetime.min.replace(tzinfo=timezone.utc),
            r["id"] is None,
            r["id"] or 0,
        )
    )
    filter_options = {
        "event_types": sorted({r["event_type"] for r in rows}),
        "task_types": sorted({r["task_type"] for r in rows if r["task_type"]}),
    }
    if event_type:
        rows = [r for r in rows if r["event_type"] == event_type]
    if task_type:
        rows = [r for r in rows if r["task_type"] == task_type]

    total = len(rows)
    start = (page - 1) * per_page
    page_rows = rows[start : start + per_page]
    return {
        "results": page_rows,
        "pagination": {
            "count": len(page_rows),
            "total": total,
            "pages": math.ceil(total / per_page) if total else 0,
        },
        "filter_options": filter_options,
    }


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
            "started_at": _iso_datetime(instance.started_at),
        }
    ]


def list_pending_tasks_for_user(
    session: Session,
    *,
    tenant_id: str | None,
    user_id: int,
    limit: int = 10,
    sort: str | None = None,
) -> list[HumanTaskModel]:
    """Home "My tasks" support. Same assignment-exists-subquery filter as
    count_pending_tasks / GetPendingTasksQuery -- NOT a wrapper around
    list_pending_tasks_for_super_admin (that returns every pending task for
    every user). tenant_id=None means all tenants for this one user_id
    (caller-verified super-admin-only). Default order is by id, matching
    GetPendingTasksQuery's order_by(HumanTaskModel.id); sort="newest" /
    "oldest" (Home, Task Review) orders by created time instead. Excludes tasks on
    suspended instances.
    """
    # tenant_id=None (all tenants) is caller-verified-super-admin-only --
    # see count_active_process_instances for why this isn't re-checked here.
    capped = max(1, min(int(limit), 50))
    pending_state = or_(
        WorkItemModel.completed.is_(False),
        WorkItemModel.id.is_(None) & HumanTaskModel.completed.is_(False),
    )
    stmt = (
        select(HumanTaskModel, WorkItemModel)
        .join(ProcessInstanceModel, ProcessInstanceModel.id == HumanTaskModel.process_instance_id)
        .outerjoin(WorkItemModel, WorkItemModel.id == HumanTaskModel.id)
        .where(
            pending_state,
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
    order_by = {
        "newest": (
            func.coalesce(WorkItemModel.created_at, HumanTaskModel.created_at).desc(),
            HumanTaskModel.id.desc(),
        ),
        "oldest": (
            func.coalesce(WorkItemModel.created_at, HumanTaskModel.created_at),
            HumanTaskModel.id,
        ),
    }.get(sort or "", (HumanTaskModel.id,))
    stmt = stmt.where(exists(exists_clause)).order_by(*order_by).limit(capped)
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
    pending_state = or_(
        WorkItemModel.completed.is_(False),
        WorkItemModel.id.is_(None) & HumanTaskModel.completed.is_(False),
    )
    stmt = (
        select(HumanTaskModel)
        .where(
            HumanTaskModel.m8f_tenant_id == tenant_id,
            HumanTaskModel.process_instance_id == process_instance_id,
            pending_state,
            exists(exists_clause),
        )
        .outerjoin(WorkItemModel, WorkItemModel.id == HumanTaskModel.id)
        .order_by(
            func.coalesce(WorkItemModel.created_at, HumanTaskModel.created_at),
            HumanTaskModel.id,
        )
    )
    tasks = list(session.scalars(stmt))
    waiting = _waiting_for(session, tenant_id=tenant_id, tasks=tasks)
    return [_open_task_row(task, waiting[task.id]) for task in tasks]


def list_pending_tasks_for_designer(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    user_id: int,
) -> list[dict[str, Any]]:
    """Pending tasks: every incomplete human task on this instance, whoever
    it is assigned to, with ``waiting_for`` and ``can_complete`` (caller is a
    candidate). Oldest-first. Empty when the instance is suspended, like
    ``list_completable_tasks_for_designer``.
    """
    instance = session.scalars(
        select(ProcessInstanceModel).where(
            ProcessInstanceModel.id == process_instance_id,
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
        )
    ).first()
    if instance is not None and instance.status == ProcessInstanceStatus.suspended.value:
        return []

    stmt = (
        select(HumanTaskModel, exists(_candidate_clause(tenant_id, user_id)))
        .where(
            HumanTaskModel.m8f_tenant_id == tenant_id,
            HumanTaskModel.process_instance_id == process_instance_id,
            HumanTaskModel.completed.is_(False),
        )
        .outerjoin(WorkItemModel, WorkItemModel.id == HumanTaskModel.id)
        .order_by(
            func.coalesce(WorkItemModel.created_at, HumanTaskModel.created_at),
            HumanTaskModel.id,
        )
    )
    pairs = list(session.execute(stmt))
    waiting = _waiting_for(session, tenant_id=tenant_id, tasks=[task for task, _ in pairs])
    return [
        {**_open_task_row(task, waiting[task.id]), "can_complete": bool(can_complete)}
        for task, can_complete in pairs
    ]


def _candidate_clause(tenant_id: str, user_id: int):
    return select(1).where(
        HumanTaskUserModel.human_task_id == HumanTaskModel.id,
        HumanTaskUserModel.user_id == user_id,
        HumanTaskUserModel.m8f_tenant_id == tenant_id,
    )


def _open_task_row(task: HumanTaskModel, waiting_for: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.id,
        "task_title": task.task_title,
        "task_name": task.task_name,
        "lane_name": task.lane_name,
        "waiting_for": waiting_for,
    }


def _waiting_for(
    session: Session, *, tenant_id: str, tasks: list[HumanTaskModel]
) -> dict[int, dict[str, Any]]:
    """Human task id -> who it is waiting for: ``{type, label, usernames}``.
    type is ``user`` (claimed, or a single candidate), ``group`` (lane group;
    groups carry the role permissions), ``initiator``, ``users`` (several
    candidates, no lane group) or ``unassigned``. Two batched queries.
    """
    from m8flow_bpmn_core.models.group import GroupModel
    from m8flow_bpmn_core.models.user import UserModel

    if not tasks:
        return {}
    task_ids = [task.id for task in tasks]
    candidates: dict[int, list[tuple[int, str, str | None]]] = {}
    for task_id, uid, display_name, username, added_by in session.execute(
        select(
            HumanTaskUserModel.human_task_id,
            UserModel.id,
            UserModel.display_name,
            UserModel.username,
            HumanTaskUserModel.added_by,
        )
        .join(UserModel, UserModel.id == HumanTaskUserModel.user_id)
        .where(
            HumanTaskUserModel.human_task_id.in_(task_ids),
            HumanTaskUserModel.m8f_tenant_id == tenant_id,
        )
        .order_by(UserModel.username)
    ):
        candidates.setdefault(task_id, []).append((uid, display_name or username, added_by))

    group_ids = {task.lane_assignment_id for task in tasks if task.lane_assignment_id}
    group_name_by_id = (
        {
            gid: name
            for gid, name in session.execute(
                select(GroupModel.id, GroupModel.name).where(GroupModel.id.in_(group_ids))
            )
        }
        if group_ids
        else {}
    )

    out: dict[int, dict[str, Any]] = {}
    for task in tasks:
        rows = candidates.get(task.id, [])
        names = [name for _, name, _ in rows]
        owner = next((name for uid, name, _ in rows if uid == task.actual_owner_id), None)
        if task.actual_owner_id and owner:
            out[task.id] = {"type": "user", "label": owner, "usernames": [owner]}
        elif task.lane_assignment_id in group_name_by_id:
            label = task.lane_name or group_name_by_id[task.lane_assignment_id]
            out[task.id] = {"type": "group", "label": label, "usernames": names}
        elif rows and all(added_by == "process_initiator" for _, _, added_by in rows):
            out[task.id] = {"type": "initiator", "label": names[0], "usernames": names}
        elif len(rows) == 1:
            out[task.id] = {"type": "user", "label": names[0], "usernames": names}
        elif rows:
            out[task.id] = {"type": "users", "label": f"{len(rows)} users", "usernames": names}
        else:
            out[task.id] = {"type": "unassigned", "label": "Unassigned", "usernames": []}
    return out


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
    by ``updated_at``, then id. The response uses that updated timestamp.
    """
    from sqlalchemy.orm import aliased

    from m8flow_bpmn_core.models.user import UserModel

    completer = aliased(UserModel)
    completed_state = or_(
        WorkItemModel.completed.is_(True),
        WorkItemModel.id.is_(None) & HumanTaskModel.completed.is_(True),
    )
    stmt = (
        select(HumanTaskModel, WorkItemModel, completer.display_name, completer.username)
        .outerjoin(WorkItemModel, WorkItemModel.id == HumanTaskModel.id)
        .outerjoin(
            completer,
            completer.id
            == func.coalesce(WorkItemModel.completed_by_user_id, HumanTaskModel.completed_by_user_id),
        )
        .where(
            HumanTaskModel.m8f_tenant_id == tenant_id,
            HumanTaskModel.process_instance_id == process_instance_id,
            completed_state,
        )
        .order_by(
            func.coalesce(WorkItemModel.updated_at, HumanTaskModel.updated_at),
            HumanTaskModel.id,
        )
    )
    all_completed: list[dict[str, Any]] = []
    completed_by_me: list[dict[str, Any]] = []
    for task, work_item, completer_display, completer_username in session.execute(stmt):
        completed_by_user_id = (
            work_item.completed_by_user_id
            if work_item is not None
            else task.completed_by_user_id
        )
        updated_at = (
            work_item.updated_at or task.updated_at
            if work_item is not None
            else task.updated_at
        )
        row = {
            "id": task.id,
            "task_title": task.task_title,
            "task_name": task.task_name,
            "completed_by": completer_display or completer_username,
            "updated_at": _iso_datetime(updated_at),
        }
        all_completed.append(row)
        if completed_by_user_id == user_id:
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
    pending_state = or_(
        WorkItemModel.completed.is_(False),
        WorkItemModel.id.is_(None) & HumanTaskModel.completed.is_(False),
    )
    stmt = (
        select(func.count())
        .select_from(HumanTaskModel)
        .join(ProcessInstanceModel, ProcessInstanceModel.id == HumanTaskModel.process_instance_id)
        .outerjoin(WorkItemModel, WorkItemModel.id == HumanTaskModel.id)
        .where(
            pending_state,
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
    now: datetime | None = None,
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
            now=now,
            limit=limit,
            worker_id=worker_id,
            tenant_id=tenant_id,
        )
    except BpmnCoreError as exc:
        raise map_bpmn_error(exc) from exc


class _StartImportPolicy:
    """Lets Start record the BPMN it runs, as the pre-next-gen host did for any
    user allowed to start: grants `process_definition.import` and nothing else,
    only inside `_definition_id_for_start`. The XML is the server's own spec
    file, never request input, and the instance creation that follows still runs
    the caller's own start check. Everything else goes to the host policy.
    """

    def authorize(self, session: Session, request: api.AuthorizationRequest) -> api.AuthorizationDecision:
        if request.command_key == api.PROCESS_DEFINITION_IMPORT_COMMAND:
            return api.AuthorizationDecision(allowed=True, reason="start_records_bpmn")
        from m8flow_backend.authorization import HostAuthorizationPolicy

        return HostAuthorizationPolicy().authorize(session, request)


def _definition_id_for_start(
    session: Session, *, tenant_id: str, user_id: int, process_model_identifier: str
) -> int:
    """The definition Start runs: the model's primary BPMN as it is on disk.

    The catalog lists models and reads their status from the spec dir, so Start
    must run that same file -- as the pre-next-gen host did, recording the BPMN
    version as part of creating the instance. Resolving from the database alone
    broke Start whenever the two diverged: a clean rebuild (`down -v`) wipes the
    database but keeps the bind-mounted spec dir (M8F-566).

    Imports only when this model has not yet been imported with this exact XML:
    import re-syncs timer-start jobs, so importing on every Start would keep
    rescheduling them. Definitions are unique per (tenant, XML hash) and name
    the model imported last, so a copy with identical XML is re-pointed here
    rather than reused, or the instance would be created as the other model.
    """
    from m8flow_backend import catalog
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    found = catalog.read_primary_bpmn(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    if found is None:
        raise ApiError(
            "not_found", f"No BPMN file for process model {process_model_identifier}", 404
        )
    file_name, xml = found
    # Same digest core's import keys definitions by (full_process_model_hash).
    xml_hash = hashlib.sha256(xml.encode("utf-8")).hexdigest()

    def imported_as_this_model() -> BpmnProcessDefinitionModel | None:
        # one_or_none: (tenant, hash) is unique in core, so there is no row to pick
        # between. populate_existing: re-read after waiting on the lock below.
        definition = session.scalars(
            select(BpmnProcessDefinitionModel)
            .where(
                BpmnProcessDefinitionModel.m8f_tenant_id == tenant_id,
                BpmnProcessDefinitionModel.full_process_model_hash == xml_hash,
            )
            .execution_options(populate_existing=True)
        ).one_or_none()
        if definition is not None and definition.process_model_identifier == process_model_identifier:
            return definition
        return None

    definition = imported_as_this_model()
    if definition is not None:
        return definition.id
    if session.get_bind().dialect.name == "postgresql":
        # Two first Starts of this XML would both insert it and the loser would
        # fail on the (tenant, hash) unique key. Serialize them: the commit below
        # releases the lock and the loser then finds the winner's import.
        # SQLite already serializes writers. 64-bit key (not 32-bit `hashtext`)
        # so unrelated imports practically never wait on each other; signed to
        # fit bigint, so negative keys are expected.
        key = hashlib.sha256(f"m8flow:start-import:{tenant_id}:{xml_hash}".encode()).digest()
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(key[:8], "big", signed=True)},
        )
        definition = imported_as_this_model()
    if definition is None:
        with api.authorization_policy_scope(_StartImportPolicy()):
            definition = import_definition(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                bpmn_identifier=process_model_identifier,
                source_bpmn_xml=xml,
                bpmn_name=file_name,
            )
    # Committed for the same reason as identity._write_tenant_field_3: core
    # prepares the instance in an independent session that records the BPMN
    # version snapshot too, and against this import still uncommitted it waits on
    # our row forever (PostgreSQL) or fails "database is locked" (SQLite). The
    # import stands on its own -- it is the model as published on disk.
    session.commit()
    return definition.id


# `process_instance_metadata.value` is a bounded varchar in core. Read the width from the
# model so it cannot drift.
_METADATA_VALUE_MAX_LENGTH = (
    getattr(ProcessInstanceMetadataModel.__table__.c.value.type, "length", None) or 255
)


def _stringify_metadata_value(value: Any) -> str:
    """One task-payload value as searchable instance metadata, truncated to fit.

    Unbounded, a single long form field (or any dict/list that JSON-dumps past the
    column width) fails the INSERT and takes the whole task completion down with it --
    PostgreSQL raises StringDataRightTruncation rather than silently trimming. This
    metadata drives search and list columns; the authoritative submission is kept by
    the workflow's own task data, so trimming here loses nothing that matters.
    """
    text = value if isinstance(value, str) else json.dumps(value)
    return text[:_METADATA_VALUE_MAX_LENGTH]
