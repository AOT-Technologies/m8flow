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

    def _task_sort_ts(task: object) -> float:
        val = getattr(task, "last_state_change", None)
        if isinstance(val, (int, float)):
            return float(val)
        if hasattr(val, "timestamp"):
            return val.timestamp()
        return 0.0

    def _merge_workflow_context(
        merged_data: dict[str, Any],
        workflow: Any,
        process_instance_processor_cls: Any,
    ) -> None:
        """Merge workflow state and completed-task data into the render context."""
        workflow_data = getattr(workflow, "data", None)
        if isinstance(workflow_data, dict) and workflow_data:
            _merge_context_dict(merged_data, workflow_data)

        workflow_data_objects = getattr(workflow, "data_objects", None)
        if isinstance(workflow_data_objects, dict) and workflow_data_objects:
            merged_data.update(workflow_data_objects)

        completed_tasks_with_data = process_instance_processor_cls.get_tasks_with_data(workflow)
        for completed_task in sorted(completed_tasks_with_data, key=_task_sort_ts):
            completed_task_data = getattr(completed_task, "data", None)
            if isinstance(completed_task_data, dict) and completed_task_data:
                merged_data.update(completed_task_data)

    def _task_model_instruction_data(task_model: Any) -> dict[str, Any]:
        """Merge persisted process-wide state into the task-local render context."""
        merged_data: dict[str, Any] = {}

        bpmn_process = getattr(task_model, "bpmn_process", None)
        process_json_data_hash = getattr(bpmn_process, "json_data_hash", None)
        if isinstance(process_json_data_hash, str) and process_json_data_hash:
            try:
                process_data = JsonDataModel.find_data_dict_by_hash(process_json_data_hash)
            except JsonDataModelNotFoundError:
                process_data = {}

            if isinstance(process_data, dict) and process_data:
                _merge_context_dict(merged_data, process_data)

        process_instance_id = getattr(task_model, "process_instance_id", None)
        if isinstance(process_instance_id, int):
            from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
            from spiffworkflow_backend.services.process_instance_processor import ProcessInstanceProcessor

            process_instance = ProcessInstanceModel.query.filter_by(id=process_instance_id).first()
            if process_instance is not None:
                try:
                    processor = ProcessInstanceProcessor(
                        process_instance,
                        include_task_data_for_completed_tasks=True,
                        include_completed_subprocesses=True,
                    )
                except Exception:
                    processor = None
                if processor is not None:
                    _merge_workflow_context(merged_data, processor.bpmn_process_instance, ProcessInstanceProcessor)

        task_data = task_model.get_data()
        if isinstance(task_data, dict) and task_data:
            merged_data.update(task_data)

        return merged_data

    def patched_render_instructions_for_end_user(  # noqa: ANN001
        cls,
        task=None,
        extensions=None,
        task_data=None,
    ) -> str:
        if (
            task_data is None
            and task is not None
            and hasattr(task, "get_data")
            and hasattr(task, "properties_json")
            and hasattr(task, "bpmn_process")
        ):
            task_data = _task_model_instruction_data(task)
        return original_render_instructions_for_end_user(cls, task, extensions, task_data)

    JinjaService.render_instructions_for_end_user = classmethod(patched_render_instructions_for_end_user)
    _PATCHED = True
