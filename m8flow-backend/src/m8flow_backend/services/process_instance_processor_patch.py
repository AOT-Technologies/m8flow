from __future__ import annotations

import re
from collections.abc import Mapping

from flask import current_app

from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_identifier

_PATCHED = False


def _task_sort_ts(task: object) -> float:
    val = getattr(task, "last_state_change", None)
    if isinstance(val, (int, float)):
        return float(val)
    if hasattr(val, "timestamp"):
        return val.timestamp()
    return 0.0


def _lane_owners_mapping(task: object) -> Mapping[str, object] | None:
    """
    Resolve lane-owner data from task-local state first, then workflow-level state.

    Downstream user tasks created after additional engine steps or Celery
    rehydration may no longer have ``lane_owners`` on ``task.data`` even though
    the initial script task stored it in workflow-level data objects.
    """
    task_data = getattr(task, "data", None)
    if isinstance(task_data, Mapping):
        lane_owners = task_data.get("lane_owners")
        if isinstance(lane_owners, Mapping):
            return lane_owners

    task_workflow = getattr(task, "workflow", None)
    if task_workflow is None:
        return None

    workflow_data = getattr(task_workflow, "data", None)
    if isinstance(workflow_data, Mapping):
        workflow_data_objects = workflow_data.get("data_objects")
        if isinstance(workflow_data_objects, Mapping):
            lane_owners = workflow_data_objects.get("lane_owners")
            if isinstance(lane_owners, Mapping):
                return lane_owners

        lane_owners = workflow_data.get("lane_owners")
        if isinstance(lane_owners, Mapping):
            return lane_owners

    workflow_data_objects = getattr(task_workflow, "data_objects", None)
    if isinstance(workflow_data_objects, Mapping):
        lane_owners = workflow_data_objects.get("lane_owners")
        if isinstance(lane_owners, Mapping):
            return lane_owners

    return None


def apply() -> None:
    """Patch lane-owner resolution so task potential owners stay tenant-aware."""
    global _PATCHED
    if _PATCHED:
        return

    from SpiffWorkflow.task import Task as SpiffTask  # type: ignore
    from spiffworkflow_backend.interfaces import PotentialOwnerIdList
    from spiffworkflow_backend.models.human_task_user import HumanTaskUserAddedBy
    from spiffworkflow_backend.services.process_instance_processor import CustomBpmnScriptEngine
    from spiffworkflow_backend.services.process_instance_processor import ProcessInstanceProcessor
    from spiffworkflow_backend.services.user_service import UserService

    def patched_get_potential_owners_from_task(self: ProcessInstanceProcessor, task: SpiffTask) -> PotentialOwnerIdList:
        """Resolve guest, initiator, lane-assignment, and lane-owner users within the current tenant."""
        task_spec = task.task_spec
        task_lane = "process_initiator"

        if current_app.config.get("SPIFFWORKFLOW_BACKEND_USE_LANES_FOR_TASK_ASSIGNMENT") is not False:
            if task_spec.lane is not None and task_spec.lane != "":
                task_lane = task_spec.lane

        potential_owners = []
        lane_assignment_id = None

        if "allowGuest" in task.task_spec.extensions and task.task_spec.extensions["allowGuest"] == "true":
            guest_user = UserService.find_or_create_guest_user()
            potential_owners = [{"added_by": HumanTaskUserAddedBy.guest.value, "user_id": guest_user.id}]
        elif re.match(r"(process.?)initiator", task_lane, re.IGNORECASE):
            potential_owners = [
                {
                    "added_by": HumanTaskUserAddedBy.process_initiator.value,
                    "user_id": self.process_instance_model.process_initiator_id,
                }
            ]
        else:
            group_model = UserService.find_or_create_group(task_lane)
            lane_assignment_id = group_model.id
            lane_owners = _lane_owners_mapping(task)
            if isinstance(lane_owners, Mapping) and task_lane in lane_owners:
                lane_owner_identifiers = lane_owners[task_lane]
                if not isinstance(lane_owner_identifiers, list):
                    lane_owner_identifiers = []
                for username_identifier in lane_owner_identifiers:
                    for lane_owner_user in find_users_for_current_tenant_by_identifier(username_identifier):
                        potential_owners.append(
                            {"added_by": HumanTaskUserAddedBy.lane_owner.value, "user_id": lane_owner_user.id}
                        )
                self.raise_if_no_potential_owners(
                    potential_owners,
                    (
                        "No users found in task data lane owner list for lane:"
                        f" {task_lane}. The user list used:"
                        f" {lane_owner_identifiers}"
                    ),
                )
            else:
                potential_owners = [
                    {"added_by": HumanTaskUserAddedBy.lane_assignment.value, "user_id": assignment.user_id}
                    for assignment in group_model.user_group_assignments
                ]

        return {
            "potential_owners": potential_owners,
            "lane_assignment_id": lane_assignment_id,
        }

    original_evaluate = CustomBpmnScriptEngine.evaluate

    def patched_evaluate(self, task, expression: str, external_context: dict | None = None):  # noqa: ANN001
        """Expose workflow-level and completed-task data to script and DMN evaluation."""
        merged_external_context = {}
        task_workflow = getattr(task, "workflow", None)

        workflow_data = getattr(task_workflow, "data", None)
        if isinstance(workflow_data, dict) and workflow_data:
            workflow_data_objects_from_data = workflow_data.get("data_objects")
            if isinstance(workflow_data_objects_from_data, dict) and workflow_data_objects_from_data:
                merged_external_context.update(workflow_data_objects_from_data)
            merged_external_context.update({k: v for k, v in workflow_data.items() if k != "data_objects"})

        workflow_data_objects = getattr(task_workflow, "data_objects", None)
        if isinstance(workflow_data_objects, dict) and workflow_data_objects:
            merged_external_context.update(workflow_data_objects)

        if task_workflow is not None and hasattr(ProcessInstanceProcessor, "get_tasks_with_data"):
            completed_tasks_with_data = ProcessInstanceProcessor.get_tasks_with_data(task_workflow)
            for completed_task in sorted(
                completed_tasks_with_data,
                key=_task_sort_ts,
            ):
                completed_task_data = getattr(completed_task, "data", None)
                if isinstance(completed_task_data, dict) and completed_task_data:
                    merged_external_context.update(completed_task_data)

        if isinstance(external_context, dict) and external_context:
            merged_external_context.update(external_context)

        return original_evaluate(self, task, expression, external_context=merged_external_context)

    CustomBpmnScriptEngine.evaluate = patched_evaluate
    ProcessInstanceProcessor.get_potential_owners_from_task = patched_get_potential_owners_from_task
    _PATCHED = True
