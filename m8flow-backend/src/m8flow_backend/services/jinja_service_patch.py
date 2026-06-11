from __future__ import annotations

from typing import Any

from spiffworkflow_backend.services.jinja_service import JinjaService

_PATCHED = False


def apply() -> None:
    """Patch Jinja instruction rendering so task pages can see process-level variables."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.models.json_data import JsonDataModel
    from spiffworkflow_backend.models.json_data import JsonDataModelNotFoundError

    original_render_instructions_for_end_user = JinjaService.render_instructions_for_end_user.__func__

    def _merge_context_dict(merged_data: dict[str, Any], context_data: dict[str, Any]) -> None:
        context_data_objects = context_data.get("data_objects")
        if isinstance(context_data_objects, dict) and context_data_objects:
            merged_data.update(context_data_objects)
        merged_data.update({k: v for k, v in context_data.items() if k != "data_objects"})

    def _task_model_instruction_data(task_model: Any) -> dict[str, Any]:
        """Merge persisted process-wide state into the task-local render context.

        Build order (each layer overrides the previous):
          1. bpmn_process.json_data_hash  — workflow.data (process-level / data-objects)
          2. All COMPLETED TaskModels for this process instance, ordered by end_in_seconds
          3. The current task's own stored data
        """
        merged_data: dict[str, Any] = {}

        # 1. Process-level data (workflow.data / data objects) stored on the BpmnProcessModel
        bpmn_process = getattr(task_model, "bpmn_process", None)
        process_json_data_hash = getattr(bpmn_process, "json_data_hash", None)
        if isinstance(process_json_data_hash, str) and process_json_data_hash:
            try:
                process_data = JsonDataModel.find_data_dict_by_hash(process_json_data_hash)
            except JsonDataModelNotFoundError:
                process_data = {}
            if isinstance(process_data, dict) and process_data:
                _merge_context_dict(merged_data, process_data)

        # 2. Data from every completed task in this process instance, ordered by completion time.
        #    This captures postScript-computed variables that live in task-level json_data rather
        #    than in the shared workflow.data dict.
        process_instance_id = getattr(task_model, "process_instance_id", None)
        current_task_guid = getattr(task_model, "guid", None)
        if isinstance(process_instance_id, int):
            completed_tasks: list[Any] = []
            try:
                from spiffworkflow_backend.models.task import TaskModel as _TaskModel

                completed_tasks = (
                    _TaskModel.query.filter_by(
                        process_instance_id=process_instance_id,
                        state="COMPLETED",
                    )
                    .order_by(_TaskModel.end_in_seconds.asc())
                    .all()
                )
            except Exception:
                completed_tasks = []
            for completed_task in completed_tasks:
                if completed_task.guid == current_task_guid:
                    continue
                try:
                    ct_data = completed_task.get_data()
                except Exception:
                    continue
                if isinstance(ct_data, dict) and ct_data:
                    merged_data.update(ct_data)

            if not completed_tasks:
                try:
                    from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
                    from spiffworkflow_backend.services.process_instance_processor import (
                        ProcessInstanceProcessor,
                    )

                    process_instance_model = ProcessInstanceModel.query.filter_by(id=process_instance_id).first()
                    if process_instance_model is not None:
                        processor = ProcessInstanceProcessor(
                            process_instance_model,
                            include_task_data_for_completed_tasks=True,
                            include_completed_subprocesses=True,
                        )
                        historical_process_instance = getattr(processor, "bpmn_process_instance", None)
                        historical_process_data = getattr(historical_process_instance, "data", None)
                        historical_data_objects = getattr(historical_process_instance, "data_objects", None)
                        historical_context: dict[str, Any] = {}
                        if isinstance(historical_data_objects, dict) and historical_data_objects:
                            historical_context["data_objects"] = historical_data_objects
                        if isinstance(historical_process_data, dict) and historical_process_data:
                            historical_context.update(historical_process_data)
                        if historical_context:
                            _merge_context_dict(merged_data, historical_context)

                        get_tasks_with_data = getattr(ProcessInstanceProcessor, "get_tasks_with_data", None)
                        if callable(get_tasks_with_data):
                            historical_tasks = get_tasks_with_data(historical_process_instance)
                            if isinstance(historical_tasks, list):
                                sorted_historical_tasks = sorted(
                                    historical_tasks,
                                    key=lambda task: getattr(task, "last_state_change", 0) or 0,
                                )
                                for historical_task in sorted_historical_tasks:
                                    historical_task_data = getattr(historical_task, "data", None)
                                    if isinstance(historical_task_data, dict) and historical_task_data:
                                        merged_data.update(historical_task_data)
                except Exception:
                    pass

        # 3. The current task's own stored data overrides everything accumulated above.
        task_model_data = getattr(task_model, "data", None)
        task_data = task_model_data if task_model_data is not None else task_model.get_data()
        if isinstance(task_data, dict) and task_data:
            merged_data.update(task_data)

        return merged_data

    def patched_render_instructions_for_end_user(  # noqa: ANN001
        cls,
        task=None,
        extensions=None,
        task_data=None,
    ) -> str:
        try:
            if (
                task_data is None
                and task is not None
                and hasattr(task, "get_data")
                and hasattr(task, "properties_json")
                and hasattr(task, "bpmn_process")
            ):
                task_data = _task_model_instruction_data(task)
            return original_render_instructions_for_end_user(cls, task, extensions, task_data)
        except Exception as exc:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "Failed to render instructions for end user. Showing task without instructions. Error: %s",
                exc,
            )
            return ""

    JinjaService.render_instructions_for_end_user = classmethod(patched_render_instructions_for_end_user)
    _PATCHED = True
