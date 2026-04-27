from __future__ import annotations

from flask import current_app

_PATCHED = False


def apply() -> None:
    """Patch process-instance rehydration so completed form data survives downstream gateway evaluation."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.data_migrations.process_instance_migrator import ProcessInstanceMigrator
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.services.process_instance_processor import ProcessInstanceProcessor
    from spiffworkflow_backend.services.process_instance_queue_service import ProcessInstanceQueueService
    from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService
    from spiffworkflow_backend.services.workflow_execution_service import TaskRunnability

    original_update_form_task_data = ProcessInstanceService.update_form_task_data

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
        workflow_data.update(submitted_form_data)

        workflow_data_objects = getattr(workflow, "data_objects", None)
        if isinstance(workflow_data_objects, dict):
            workflow_data_objects.update(submitted_form_data)

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
            for completed_task in sorted(completed_tasks_with_data, key=lambda task: task.last_state_change or 0):
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

    ProcessInstanceService.update_form_task_data = patched_update_form_task_data
    ProcessInstanceService.run_process_instance_with_processor = patched_run_process_instance_with_processor
    _PATCHED = True
