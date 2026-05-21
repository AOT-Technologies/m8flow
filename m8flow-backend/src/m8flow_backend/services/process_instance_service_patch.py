from __future__ import annotations

import hashlib
import time

from flask import current_app
from flask import g

_PATCHED = False


def _task_sort_ts(task: object) -> float:
    val = getattr(task, "last_state_change", None)
    if isinstance(val, (int, float)):
        return float(val)
    if hasattr(val, "timestamp"):
        return val.timestamp()
    return 0.0


def _normalized_string_attr(obj: object, attr_name: str) -> str | None:
    value = getattr(obj, attr_name, None)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if normalized:
        return normalized
    return None


def _safe_potential_owner_label(user: object) -> str | None:
    """Return the best available stable label for a potential owner."""
    for attr_name in ("email", "username", "display_name", "service_id"):
        normalized = _normalized_string_attr(user, attr_name)
        if normalized:
            return normalized

    return None


def _safe_potential_owner_usernames(human_task: object) -> str | None:
    """Serialize potential owners without assuming email is always present."""
    potential_owners = getattr(human_task, "potential_owners", None)
    if not potential_owners:
        return None

    serialized_labels: list[str] = []
    seen: set[str] = set()
    human_task_id = getattr(human_task, "id", None)
    human_task_task_id = getattr(human_task, "task_id", None)

    for potential_owner in potential_owners:
        label = _safe_potential_owner_label(potential_owner)
        if label is None:
            current_app.logger.warning(
                "Skipping potential owner with no usable identifier for human_task id=%s task_id=%s user_id=%s",
                human_task_id,
                human_task_task_id,
                getattr(potential_owner, "id", None),
            )
            continue

        if label in seen:
            continue
        seen.add(label)
        serialized_labels.append(label)

    if not serialized_labels:
        return None

    return ",".join(serialized_labels)


def _raise_lane_assignment_api_error(
    process_instance: object,
    exc: Exception,
    *,
    message_prefix: str,
    handle_error: bool,
) -> None:
    """Rollback queued work and convert lane-assignment failures into a user-facing API error."""
    from spiffworkflow_backend.exceptions.api_error import ApiError
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.services.error_handling_service import ErrorHandlingService

    db.session.rollback()
    if handle_error:
        ErrorHandlingService.handle_error(process_instance, exc)
    raise ApiError(
        error_code="task_lane_assignment_error",
        message=f"{message_prefix} {exc}",
        status_code=400,
    ) from exc


def _validate_queued_follow_up_work(processor: object, *, handle_error: bool = False) -> None:
    """Run immediate engine work during queued submission so assignment failures surface to the submitter."""
    from spiffworkflow_backend.services.process_instance_processor import NoPotentialOwnersForTaskError

    try:
        processor.do_engine_steps(  # type: ignore[attr-defined]
            save=True,
            execution_strategy_name="run_until_user_message",
            should_schedule_waiting_timer_events=False,
        )
    except NoPotentialOwnersForTaskError as exc:
        _raise_lane_assignment_api_error(
            processor.process_instance_model,  # type: ignore[attr-defined]
            exc,
            message_prefix="Task submission could not continue.",
            handle_error=handle_error,
        )


def _validate_queued_process_start(process_instance: object, *, handle_error: bool = False) -> None:
    """Run immediate engine work during queued process start so assignment failures surface to the starter."""
    from spiffworkflow_backend.services.process_instance_processor import NoPotentialOwnersForTaskError
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService

    try:
        ProcessInstanceService.run_process_instance_with_processor(
            process_instance,
            execution_strategy_name="run_until_user_message",
            should_schedule_waiting_timer_events=False,
        )
    except NoPotentialOwnersForTaskError as exc:
        _raise_lane_assignment_api_error(
            process_instance,
            exc,
            message_prefix="Process start could not continue.",
            handle_error=handle_error,
        )


def apply() -> None:
    """Patch ProcessInstanceService: record BPMN XML version at creation time and fix completed-task data rehydration."""
    global _PATCHED
    if _PATCHED:
        return

    import sqlalchemy as sa

    from spiffworkflow_backend.data_migrations.process_instance_migrator import ProcessInstanceMigrator
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.services.process_instance_processor import ProcessInstanceProcessor
    from spiffworkflow_backend.services.process_instance_queue_service import ProcessInstanceQueueService
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService
    from spiffworkflow_backend.services.spec_file_service import SpecFileService
    from spiffworkflow_backend.services.workflow_execution_service import TaskRunnability

    original_create_process_instance = ProcessInstanceService.create_process_instance
    original_spiff_task_to_api_task = getattr(ProcessInstanceService, "spiff_task_to_api_task", None)
    original_update_form_task_data = ProcessInstanceService.update_form_task_data

    @classmethod  # type: ignore[misc]
    def patched_create_process_instance(cls, process_model, user, start_configuration=None, load_bpmn_process_model: bool = True):
        process_instance_model, start_config = original_create_process_instance(
            process_model,
            user,
            start_configuration=start_configuration,
            load_bpmn_process_model=load_bpmn_process_model,
        )

        primary_file_name = getattr(process_model, "primary_file_name", None)
        if primary_file_name:
            try:
                raw_bytes = SpecFileService.get_data(process_model, primary_file_name)
                xml_text = raw_bytes.decode("utf-8")
                if xml_text:
                    # Upstream only adds the ProcessInstanceModel to the session; it doesn't flush/commit.
                    # We need an id + tenant id before we can store the version reference.
                    db.session.flush()
                    tenant_id = getattr(process_instance_model, "m8f_tenant_id", None)
                    if tenant_id:
                        bpmn_hash = hashlib.sha256(xml_text.encode("utf-8")).hexdigest()
                        model_id = getattr(process_model, "id", "")

                        # Upsert: insert if the (tenant, model, hash) combo doesn't exist yet.
                        db.session.execute(
                            sa.text(
                                """
                                INSERT INTO process_model_bpmn_version
                                  (m8f_tenant_id, process_model_identifier, bpmn_xml_hash, bpmn_xml_file_contents, created_at_in_seconds)
                                VALUES
                                  (:m8f_tenant_id, :process_model_identifier, :bpmn_xml_hash, :bpmn_xml_file_contents, :created_at_in_seconds)
                                ON CONFLICT(m8f_tenant_id, process_model_identifier, bpmn_xml_hash) DO NOTHING
                                """
                            ),
                            {
                                "m8f_tenant_id": tenant_id,
                                "process_model_identifier": model_id,
                                "bpmn_xml_hash": bpmn_hash,
                                "bpmn_xml_file_contents": xml_text,
                                "created_at_in_seconds": round(time.time()),
                            },
                        )

                        # Retrieve the version id (may have been inserted just now or previously).
                        version_row = db.session.execute(
                            sa.text(
                                """
                                SELECT id FROM process_model_bpmn_version
                                WHERE m8f_tenant_id = :m8f_tenant_id
                                  AND process_model_identifier = :process_model_identifier
                                  AND bpmn_xml_hash = :bpmn_xml_hash
                                LIMIT 1
                                """
                            ),
                            {
                                "m8f_tenant_id": tenant_id,
                                "process_model_identifier": model_id,
                                "bpmn_xml_hash": bpmn_hash,
                            },
                        ).first()

                        if version_row is not None:
                            process_instance_model.bpmn_version_id = version_row[0]
            except Exception:
                current_app.logger.warning(
                    "Failed to record BPMN version for process instance %s (process_model=%s)",
                    getattr(process_instance_model, "id", None),
                    getattr(process_model, "id", None),
                    exc_info=True,
                )

        return process_instance_model, start_config

    @classmethod
    def patched_update_form_task_data(
        cls,
        process_instance,
        spiff_task,
        data: dict,
        user,
    ) -> None:
        original_update_form_task_data(process_instance, spiff_task, data, user)

        if not isinstance(data, dict) or not data:
            return

        workflow = getattr(spiff_task, "workflow", None)
        if workflow is None:
            return

        workflow_data = getattr(workflow, "data", None)
        if not isinstance(workflow_data, dict):
            return

        submitted_form_data = {key: value for key, value in data.items() if key != "data_objects"}

        existing_data_objects = workflow_data.get("data_objects")
        merged_data_objects = {}
        if isinstance(existing_data_objects, dict) and existing_data_objects:
            merged_data_objects.update(existing_data_objects)
        merged_data_objects.update(submitted_form_data)
        workflow_data["data_objects"] = merged_data_objects

        workflow_data_objects = getattr(workflow, "data_objects", None)
        if isinstance(workflow_data_objects, dict):
            workflow_data_objects.update(submitted_form_data)

    @classmethod
    def patched_complete_form_task(
        cls,
        processor,
        spiff_task,
        data: dict[str, object],
        user,
        human_task,
        execution_mode: str | None = None,
    ) -> None:
        from SpiffWorkflow.util.task import TaskState  # type: ignore
        from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer import (
            should_queue_process_instance,
        )
        from spiffworkflow_backend.helpers.spiff_enum import ProcessInstanceExecutionMode
        from spiffworkflow_backend.services.jinja_service import JinjaService
        from spiffworkflow_backend.services.process_instance_tmp_service import ProcessInstanceTmpService

        ProcessInstanceService.update_form_task_data(processor.process_instance_model, spiff_task, data, user)
        processor.complete_task(spiff_task, human_task, user=user)

        if should_queue_process_instance(execution_mode):
            _validate_queued_follow_up_work(processor, handle_error=False)
            processor.bpmn_process_instance.refresh_waiting_tasks()
            tasks = processor.bpmn_process_instance.get_tasks(state=TaskState.WAITING | TaskState.READY)
            JinjaService.add_instruction_for_end_user_if_appropriate(tasks, processor.process_instance_model.id, set())
        elif not ProcessInstanceTmpService.is_enqueued_to_run_in_the_future(processor.process_instance_model):
            execution_strategy_name = None
            if execution_mode == ProcessInstanceExecutionMode.synchronous.value:
                execution_strategy_name = "greedy"

            processor.do_engine_steps(save=True, execution_strategy_name=execution_strategy_name)

    @classmethod
    def patched_run_process_instance_with_processor(
        cls,
        process_instance,
        status_value: str | None = None,
        execution_strategy_name: str | None = None,
        should_schedule_waiting_timer_events: bool = True,
    ) -> tuple[ProcessInstanceProcessor | None, TaskRunnability]:
        processor = None
        task_runnability = TaskRunnability.unknown_if_ready_tasks
        with ProcessInstanceQueueService.dequeued(process_instance):
            ProcessInstanceMigrator.run(process_instance)
            processor = ProcessInstanceProcessor(
                process_instance,
                workflow_completed_handler=cls.schedule_next_process_model_cycle,
                include_task_data_for_completed_tasks=True,
            )
            completed_task_data = process_instance.get_data()
            if isinstance(completed_task_data, dict) and completed_task_data:
                processor.bpmn_process_instance.data.update(completed_task_data)
            completed_tasks_with_data = ProcessInstanceProcessor.get_tasks_with_data(processor.bpmn_process_instance)
            merged_data_objects = {}
            existing_data_objects = processor.bpmn_process_instance.data.get("data_objects")
            if isinstance(existing_data_objects, dict) and existing_data_objects:
                merged_data_objects.update(existing_data_objects)
            for completed_task in sorted(completed_tasks_with_data, key=_task_sort_ts):
                if isinstance(completed_task.data, dict) and completed_task.data:
                    merged_data_objects.update(completed_task.data)
            if merged_data_objects:
                processor.bpmn_process_instance.data["data_objects"] = merged_data_objects

        if status_value and cls.can_optimistically_skip(processor, status_value):
            current_app.logger.info(f"Optimistically skipped process_instance {process_instance.id}")
            return (processor, task_runnability)

        db.session.refresh(process_instance)
        if status_value is None or process_instance.status == status_value:
            task_runnability = processor.do_engine_steps(
                save=True,
                execution_strategy_name=execution_strategy_name,
                should_schedule_waiting_timer_events=should_schedule_waiting_timer_events,
            )

        return (processor, task_runnability)

    @staticmethod
    def patched_spiff_task_to_api_task(processor, spiff_task):
        from SpiffWorkflow.util.task import TaskState  # type: ignore
        from spiffworkflow_backend.exceptions.error import HumanTaskAlreadyCompletedError
        from spiffworkflow_backend.exceptions.error import HumanTaskNotFoundError
        from spiffworkflow_backend.exceptions.error import UserDoesNotHaveAccessToTaskError
        from spiffworkflow_backend.models.group import GroupModel
        from spiffworkflow_backend.models.human_task import HumanTaskModel
        from spiffworkflow_backend.models.process_instance_event import ProcessInstanceEventModel
        from spiffworkflow_backend.models.process_instance_event import ProcessInstanceEventType
        from spiffworkflow_backend.models.task import Task
        from spiffworkflow_backend.services.authorization_service import AuthorizationService

        if callable(original_spiff_task_to_api_task):
            try:
                return original_spiff_task_to_api_task(processor, spiff_task)
            except TypeError as exc:
                if "expected str instance" not in str(exc) or "NoneType found" not in str(exc):
                    raise

        task_type = spiff_task.task_spec.description
        task_guid = str(spiff_task.id)

        props = {}
        if hasattr(spiff_task.task_spec, "extensions"):
            for key, val in spiff_task.task_spec.extensions.items():
                props[key] = val

        if hasattr(spiff_task.task_spec, "lane"):
            lane = spiff_task.task_spec.lane
        else:
            lane = None

        can_complete = False
        try:
            AuthorizationService.assert_user_can_complete_task(processor.process_instance_model.id, task_guid, g.user)
            can_complete = True
        except HumanTaskAlreadyCompletedError:
            can_complete = False
        except HumanTaskNotFoundError:
            can_complete = False
        except UserDoesNotHaveAccessToTaskError:
            can_complete = False

        assigned_user_group_identifier = None
        potential_owner_usernames = None
        if can_complete is False:
            human_task = HumanTaskModel.query.filter_by(task_id=task_guid).first()
            if human_task is not None:
                if human_task.lane_assignment_id is not None:
                    group = GroupModel.query.filter_by(id=human_task.lane_assignment_id).first()
                    if group is not None:
                        assigned_user_group_identifier = group.identifier
                elif len(human_task.potential_owners) > 0:
                    potential_owner_usernames = _safe_potential_owner_usernames(human_task)

        parent_id = None
        if spiff_task.parent:
            parent_id = spiff_task.parent.id

        serialized_task_spec = processor.serialize_task_spec(spiff_task.task_spec)

        error_message = None
        error_event = ProcessInstanceEventModel.query.filter_by(
            task_guid=task_guid, event_type=ProcessInstanceEventType.task_failed.value
        ).first()
        if error_event:
            error_message = error_event.error_details[-1].message

        return Task(
            spiff_task.id,
            spiff_task.task_spec.bpmn_id,
            spiff_task.task_spec.bpmn_name,
            task_type,
            TaskState.get_name(spiff_task.state),
            can_complete=can_complete,
            lane=lane,
            process_identifier=spiff_task.task_spec._wf_spec.name,
            process_instance_id=processor.process_instance_model.id,
            process_model_identifier=processor.process_model_identifier,
            process_model_display_name=processor.process_model_display_name,
            properties=props,
            parent=parent_id,
            event_definition=serialized_task_spec.get("event_definition"),
            error_message=error_message,
            assigned_user_group_identifier=assigned_user_group_identifier,
            potential_owner_usernames=potential_owner_usernames,
        )

    ProcessInstanceService.create_process_instance = patched_create_process_instance  # type: ignore[assignment]
    ProcessInstanceService.complete_form_task = patched_complete_form_task
    ProcessInstanceService.spiff_task_to_api_task = patched_spiff_task_to_api_task
    ProcessInstanceService.update_form_task_data = patched_update_form_task_data
    ProcessInstanceService.run_process_instance_with_processor = patched_run_process_instance_with_processor
    _PATCHED = True
