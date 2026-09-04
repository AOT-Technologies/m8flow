from __future__ import annotations

import hashlib
import time

from flask import current_app

from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.tenancy import (
    is_super_admin_request,
    reset_context_tenant_id,
    set_context_tenant_id,
)

_PATCHED = False


def _task_sort_ts(task: object) -> float:
    val = getattr(task, "last_state_change", None)
    if isinstance(val, (int, float)):
        return float(val)
    if hasattr(val, "timestamp"):
        return val.timestamp()
    return 0.0


def _seed_processor_with_completed_data(processor: object, process_instance: object) -> None:
    """Merge completed-task data into the processor so re-runs see executed values."""
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


def _extract_api_error_from_exception_tree(exc: BaseException | None) -> Exception | None:
    """Return the first nested ApiError reachable through wrapped workflow exceptions."""
    from spiffworkflow_backend.exceptions.api_error import ApiError

    if exc is None:
        return None

    seen_ids: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        current_id = id(current)
        if current_id in seen_ids:
            continue
        seen_ids.add(current_id)

        if isinstance(current, ApiError):
            return current

        nested_exception = getattr(current, "exception", None)
        if isinstance(nested_exception, BaseException):
            pending.append(nested_exception)

        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            pending.append(cause)

        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException):
            pending.append(context)

        nested_exceptions = getattr(current, "exceptions", None)
        if isinstance(nested_exceptions, tuple | list):
            pending.extend(item for item in nested_exceptions if isinstance(item, BaseException))

    return None


def _raise_nested_api_error(
    process_instance: object,
    wrapped_exc: Exception,
    api_error: Exception,
    *,
    handle_error: bool,
) -> None:
    """Rollback queued work and re-raise the underlying API error for user-facing task submit failures."""
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.services.error_handling_service import ErrorHandlingService

    db.session.rollback()
    if handle_error:
        ErrorHandlingService.handle_error(process_instance, wrapped_exc)
    raise api_error from wrapped_exc


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
    except Exception as exc:
        api_error = _extract_api_error_from_exception_tree(exc)
        if api_error is None:
            raise
        _raise_nested_api_error(
            processor.process_instance_model,  # type: ignore[attr-defined]
            exc,
            api_error,
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
    """Record BPMN versions at create; seed completed data on run; telemetry + queue preflight."""
    global _PATCHED
    if _PATCHED:
        return

    import importlib

    import sqlalchemy as sa

    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.services.process_instance_processor import ProcessInstanceProcessor
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService
    from spiffworkflow_backend.services.spec_file_service import SpecFileService
    from spiffworkflow_backend.services.workflow_execution_service import TaskRunnability

    original_create_process_instance = ProcessInstanceService.create_process_instance
    original_complete_form_task = getattr(ProcessInstanceService, "complete_form_task", None)
    original_run_process_instance_with_processor = getattr(
        ProcessInstanceService, "run_process_instance_with_processor", None
    )
    original_spiff_task_to_api_task = getattr(ProcessInstanceService, "spiff_task_to_api_task", None)
    original_update_form_task_data = ProcessInstanceService.update_form_task_data
    original_schedule_next_process_model_cycle = ProcessInstanceService.schedule_next_process_model_cycle
    original_terminate = getattr(ProcessInstanceProcessor, "terminate", None)

    service_module = importlib.import_module("spiffworkflow_backend.services.process_instance_service")
    processor_module = importlib.import_module("spiffworkflow_backend.services.process_instance_processor")

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
                    # Need a flushed id + tenant before writing the version row.
                    db.session.flush()
                    tenant_id = getattr(process_instance_model, "m8f_tenant_id", None)
                    if tenant_id:
                        bpmn_hash = hashlib.sha256(xml_text.encode("utf-8")).hexdigest()
                        model_id = getattr(process_model, "id", "")

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
        """Complete form with task telemetry and queued follow-up preflight."""
        if not callable(original_complete_form_task):
            raise RuntimeError("ProcessInstanceService.complete_form_task is missing")

        # A master-realm super-admin can complete a task from any tenant while
        # intentionally having no request tenant. Upstream completion writes
        # tenant-scoped event rows, so bind those writes to the already
        # authorized process instance instead of leaving their tenant NULL.
        tenant_context_token = None
        process_tenant_id = getattr(processor.process_instance_model, "m8f_tenant_id", None)
        if (
            is_super_admin_request()
            and current_tenant_id_or_none() is None
            and isinstance(process_tenant_id, str)
            and process_tenant_id.strip()
        ):
            tenant_context_token = set_context_tenant_id(process_tenant_id.strip())

        original_complete_task = processor.complete_task

        def complete_task_with_telemetry(*args, **kwargs):
            result = original_complete_task(*args, **kwargs)
            try:
                from m8flow_telemetry.metrics import record_task_completed

                tenant_metric_id = getattr(processor.process_instance_model, "m8f_tenant_id", None)
                task_type = getattr(getattr(human_task, "task_type", None), "value", None) or getattr(
                    human_task, "task_type", "unknown"
                )
                record_task_completed(
                    str(tenant_metric_id) if tenant_metric_id else None, task_type=str(task_type)
                )
            except ImportError:
                pass
            return result

        previous_should_queue = getattr(service_module, "should_queue_process_instance", None)
        if not callable(previous_should_queue):
            from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer import (
                should_queue_process_instance as producer_should_queue,
            )

            previous_should_queue = producer_should_queue
            service_module.should_queue_process_instance = producer_should_queue

        def should_queue_with_follow_up_preflight(mode: str | None = None) -> bool:
            will_queue = previous_should_queue(mode)
            if will_queue:
                _validate_queued_follow_up_work(processor, handle_error=False)
            return will_queue

        processor.complete_task = complete_task_with_telemetry
        service_module.should_queue_process_instance = should_queue_with_follow_up_preflight
        try:
            return original_complete_form_task(
                processor, spiff_task, data, user, human_task, execution_mode
            )
        finally:
            processor.complete_task = original_complete_task
            service_module.should_queue_process_instance = previous_should_queue
            if tenant_context_token is not None:
                reset_context_tenant_id(tenant_context_token)

    @classmethod
    def patched_schedule_next_process_model_cycle(cls, process_instance_model) -> None:
        # Invoked once when an instance reaches completed (workflow_completed_handler).
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
        """Run with completed-task data loaded and data objects seeded."""
        if not callable(original_run_process_instance_with_processor):
            raise RuntimeError(
                "ProcessInstanceService.run_process_instance_with_processor is missing"
            )

        # run_process_instance_with_processor constructs ProcessInstanceProcessor from this module.
        if not hasattr(service_module, "ProcessInstanceProcessor"):
            service_module.ProcessInstanceProcessor = processor_module.ProcessInstanceProcessor
        OriginalProcessor = service_module.ProcessInstanceProcessor

        class _SeedingProcessor(OriginalProcessor):
            def __init__(self, process_instance_model, *args, **kwargs):
                kwargs["include_task_data_for_completed_tasks"] = True
                super().__init__(process_instance_model, *args, **kwargs)
                _seed_processor_with_completed_data(self, process_instance_model)

        previous_processor = service_module.ProcessInstanceProcessor
        service_module.ProcessInstanceProcessor = _SeedingProcessor
        try:
            return original_run_process_instance_with_processor(
                process_instance,
                status_value=status_value,
                execution_strategy_name=execution_strategy_name,
                should_schedule_waiting_timer_events=should_schedule_waiting_timer_events,
            )
        finally:
            service_module.ProcessInstanceProcessor = previous_processor

    @staticmethod
    def patched_spiff_task_to_api_task(processor, spiff_task):
        """Prefer usernames for potential owners when emails are unavailable."""
        from spiffworkflow_backend.models.human_task import HumanTaskModel

        def _rewrite_potential_owners(task: object) -> object:
            if getattr(task, "can_complete", True):
                return task
            human_task = HumanTaskModel.query.filter_by(task_id=str(spiff_task.id)).first()
            if human_task is None or human_task.lane_assignment_id is not None:
                return task
            if not getattr(human_task, "potential_owners", None):
                return task
            task.potential_owner_usernames = _potential_owner_usernames_from_human_task(human_task)
            return task

        def _coerce_missing_owner_emails() -> list[tuple[object, object]]:
            restores: list[tuple[object, object]] = []
            human_task = HumanTaskModel.query.filter_by(task_id=str(spiff_task.id)).first()
            if human_task is None:
                return restores
            for owner in getattr(human_task, "potential_owners", []) or []:
                if getattr(owner, "email", None) is None:
                    restores.append((owner, owner.email))
                    owner.email = getattr(owner, "username", None) or ""
            return restores

        if not callable(original_spiff_task_to_api_task):
            raise RuntimeError("ProcessInstanceService.spiff_task_to_api_task is missing")

        try:
            task = original_spiff_task_to_api_task(processor, spiff_task)
        except TypeError as exc:
            message = str(exc)
            if "expected str instance" not in message or "NoneType found" not in message:
                raise
            restores = _coerce_missing_owner_emails()
            try:
                task = original_spiff_task_to_api_task(processor, spiff_task)
            finally:
                for owner, previous_email in restores:
                    owner.email = previous_email

        return _rewrite_potential_owners(task)

    ProcessInstanceService.create_process_instance = patched_create_process_instance  # type: ignore[assignment]
    ProcessInstanceService.complete_form_task = patched_complete_form_task
    ProcessInstanceService.spiff_task_to_api_task = patched_spiff_task_to_api_task
    ProcessInstanceService.update_form_task_data = patched_update_form_task_data
    ProcessInstanceService.run_process_instance_with_processor = patched_run_process_instance_with_processor
    ProcessInstanceService.schedule_next_process_model_cycle = patched_schedule_next_process_model_cycle
    ProcessInstanceProcessor.terminate = patched_terminate
    _PATCHED = True
