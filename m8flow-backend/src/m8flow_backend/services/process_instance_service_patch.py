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


def _seed_processor_with_completed_data(processor: object, process_instance: object) -> None:
    """Seed the processor's workflow data with the instance's completed-task data and the
    union of its data objects (existing + each completed task's, oldest-first), so readonly
    views and re-runs see the values the instance actually executed with."""
    from spiffworkflow_backend.services.process_instance_processor import ProcessInstanceProcessor

    completed_task_data = process_instance.get_data()
    if isinstance(completed_task_data, dict) and completed_task_data:
        processor.bpmn_process_instance.data.update(completed_task_data)

    merged_data_objects: dict = {}
    existing_data_objects = processor.bpmn_process_instance.data.get("data_objects")
    if isinstance(existing_data_objects, dict) and existing_data_objects:
        merged_data_objects.update(existing_data_objects)
    for completed_task in sorted(
        ProcessInstanceProcessor.get_tasks_with_data(processor.bpmn_process_instance), key=_task_sort_ts
    ):
        if isinstance(completed_task.data, dict) and completed_task.data:
            merged_data_objects.update(completed_task.data)
    if merged_data_objects:
        processor.bpmn_process_instance.data["data_objects"] = merged_data_objects


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


def _normalized_username(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _potential_owner_usernames_from_human_task(human_task: object) -> str | None:
    potential_owners = getattr(human_task, "potential_owners", None)
    if not potential_owners:
        return None

    usernames: list[str] = []
    seen_usernames: set[str] = set()
    for potential_owner in potential_owners:
        username = _normalized_username(getattr(potential_owner, "username", None))
        if username is None or username in seen_usernames:
            continue
        usernames.append(username)
        seen_usernames.add(username)

    if not usernames:
        return None
    return ",".join(usernames)


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
    original_schedule_next_process_model_cycle = ProcessInstanceService.schedule_next_process_model_cycle
    original_terminate = getattr(ProcessInstanceProcessor, "terminate", None)

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

        try:
            from m8flow_telemetry.metrics import (
                record_process_instance_active_delta,
                record_process_instance_created,
            )

            tenant_metric_id = str(tenant_id) if tenant_id else None
            record_process_instance_created(tenant_metric_id)
            record_process_instance_active_delta(tenant_metric_id, 1)
        except ImportError:
            pass

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

        try:
            from m8flow_telemetry.metrics import record_task_completed

            tenant_metric_id = getattr(processor.process_instance_model, "m8f_tenant_id", None)
            task_type = getattr(getattr(human_task, "task_type", None), "value", None) or getattr(
                human_task, "task_type", "unknown"
            )
            record_task_completed(str(tenant_metric_id) if tenant_metric_id else None, task_type=str(task_type))
        except ImportError:
            pass

        if should_queue_process_instance(execution_mode):
            # m8flow preflight before follow-up work is handed to the async worker.
            _validate_queued_follow_up_work(processor, handle_error=False)
            processor.bpmn_process_instance.refresh_waiting_tasks()
            ready_or_waiting = processor.bpmn_process_instance.get_tasks(
                state=TaskState.WAITING | TaskState.READY
            )
            JinjaService.add_instruction_for_end_user_if_appropriate(
                ready_or_waiting, processor.process_instance_model.id, set()
            )
            return

        # Already queued for a future run -> nothing to execute synchronously.
        if ProcessInstanceTmpService.is_enqueued_to_run_in_the_future(processor.process_instance_model):
            return

        strategy = "greedy" if execution_mode == ProcessInstanceExecutionMode.synchronous.value else None
        processor.do_engine_steps(save=True, execution_strategy_name=strategy)

    @classmethod
    def patched_schedule_next_process_model_cycle(cls, process_instance_model) -> None:
        # ProcessInstanceProcessor.save() invokes this as the workflow_completed_handler
        # exactly once, at the moment a process instance transitions to completed —
        # the only central hook point across every call site that constructs a
        # ProcessInstanceProcessor with this handler.
        original_schedule_next_process_model_cycle(process_instance_model)

        try:
            from m8flow_telemetry.metrics import record_process_instance_terminal

            tenant_metric_id = getattr(process_instance_model, "m8f_tenant_id", None)
            record_process_instance_terminal(
                str(tenant_metric_id) if tenant_metric_id else None, outcome="completed"
            )
        except ImportError:
            pass

    def patched_terminate(self) -> None:
        if callable(original_terminate):
            original_terminate(self)

        try:
            from m8flow_telemetry.metrics import record_process_instance_terminal

            tenant_metric_id = getattr(self.process_instance_model, "m8f_tenant_id", None)
            record_process_instance_terminal(
                str(tenant_metric_id) if tenant_metric_id else None, outcome="terminated"
            )
        except ImportError:
            pass

    @classmethod
    def patched_run_process_instance_with_processor(
        cls,
        process_instance,
        status_value: str | None = None,
        execution_strategy_name: str | None = None,
        should_schedule_waiting_timer_events: bool = True,
    ) -> tuple[ProcessInstanceProcessor | None, TaskRunnability]:
        task_runnability = TaskRunnability.unknown_if_ready_tasks
        with ProcessInstanceQueueService.dequeued(process_instance):
            ProcessInstanceMigrator.run(process_instance)
            processor = ProcessInstanceProcessor(
                process_instance,
                workflow_completed_handler=cls.schedule_next_process_model_cycle,
                include_task_data_for_completed_tasks=True,
            )
            # m8flow: seed the workflow with completed-task data + merged data objects so
            # readonly views and re-runs see the values captured on the executed instance.
            _seed_processor_with_completed_data(processor, process_instance)

        skip_now = bool(status_value) and cls.can_optimistically_skip(processor, status_value)
        if skip_now:
            current_app.logger.info(f"Optimistically skipped process_instance {process_instance.id}")
            return (processor, task_runnability)

        db.session.refresh(process_instance)
        status_ready = status_value is None or process_instance.status == status_value
        if status_ready:
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
        task_spec = spiff_task.task_spec
        task_type = task_spec.description
        task_guid = str(spiff_task.id)
        props = dict(getattr(task_spec, "extensions", {}) or {})
        lane = getattr(task_spec, "lane", None)

        def _user_can_complete() -> bool:
            try:
                AuthorizationService.assert_user_can_complete_task(
                    processor.process_instance_model.id, task_guid, g.user
                )
                return True
            except (
                HumanTaskAlreadyCompletedError,
                HumanTaskNotFoundError,
                UserDoesNotHaveAccessToTaskError,
            ):
                return False

        can_complete = _user_can_complete()

        # When the current user can't complete it, surface who can (lane group or the
        # potential-owner usernames) so the UI can explain why.
        assigned_user_group_identifier = None
        potential_owner_usernames = None
        blocked_human_task = None if can_complete else HumanTaskModel.query.filter_by(task_id=task_guid).first()
        if blocked_human_task is not None:
            if blocked_human_task.lane_assignment_id is not None:
                lane_group = GroupModel.query.filter_by(id=blocked_human_task.lane_assignment_id).first()
                assigned_user_group_identifier = lane_group.identifier if lane_group is not None else None
            elif len(blocked_human_task.potential_owners) > 0:
                potential_owner_usernames = _potential_owner_usernames_from_human_task(blocked_human_task)

        parent_id = spiff_task.parent.id if spiff_task.parent else None
        serialized_task_spec = processor.serialize_task_spec(task_spec)

        failure_event = ProcessInstanceEventModel.query.filter_by(
            task_guid=task_guid, event_type=ProcessInstanceEventType.task_failed.value
        ).first()
        error_message = failure_event.error_details[-1].message if failure_event else None

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
    ProcessInstanceService.schedule_next_process_model_cycle = patched_schedule_next_process_model_cycle
    ProcessInstanceProcessor.terminate = patched_terminate
    _PATCHED = True
