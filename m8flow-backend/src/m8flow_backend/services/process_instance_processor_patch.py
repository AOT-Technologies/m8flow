from __future__ import annotations

import re
from collections.abc import Mapping

from flask import current_app

from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_identifier
from m8flow_backend.services.tenant_identity_helpers import normalize_organizational_group_identifier
from m8flow_backend.services.tenant_identity_helpers import qualify_group_identifier

_PATCHED = False


def _task_sort_ts(task: object) -> float:
    val = getattr(task, "last_state_change", None)
    if isinstance(val, (int, float)):
        return float(val)
    if hasattr(val, "timestamp"):
        return val.timestamp()
    return 0.0


def _lane_owner_identifiers_for_task(task: object, task_lane: str) -> list[str] | None:
    """Return explicit lane-owner identifiers for the task lane, if present."""
    candidate_lane_owner_maps: list[object] = []

    task_data = getattr(task, "data", None)
    if isinstance(task_data, Mapping):
        candidate_lane_owner_maps.append(task_data.get("lane_owners"))

    task_workflow = getattr(task, "workflow", None)
    workflow_data = getattr(task_workflow, "data", None)
    if isinstance(workflow_data, Mapping):
        candidate_lane_owner_maps.append(workflow_data.get("lane_owners"))
        workflow_data_objects = workflow_data.get("data_objects")
        if isinstance(workflow_data_objects, Mapping):
            candidate_lane_owner_maps.append(workflow_data_objects.get("lane_owners"))

    workflow_data_objects_attr = getattr(task_workflow, "data_objects", None)
    if isinstance(workflow_data_objects_attr, Mapping):
        candidate_lane_owner_maps.append(workflow_data_objects_attr.get("lane_owners"))

    for lane_owners in candidate_lane_owner_maps:
        if not isinstance(lane_owners, Mapping):
            continue

        lane_owner_values = lane_owners.get(task_lane)
        if not isinstance(lane_owner_values, list):
            continue

        return [value for value in lane_owner_values if isinstance(value, str)]

    return None


def _candidate_lane_group_identifiers(task_lane: str) -> list[str]:
    """Return candidate tenant-qualified group identifiers for a BPMN lane."""
    candidates: list[str] = []
    seen: set[str] = set()

    for raw_identifier in (
        normalize_organizational_group_identifier(task_lane),
        task_lane.strip(),
    ):
        if not raw_identifier:
            continue
        qualified_identifier = qualify_group_identifier(raw_identifier)
        if qualified_identifier and qualified_identifier not in seen:
            seen.add(qualified_identifier)
            candidates.append(qualified_identifier)

    return candidates


def apply() -> None:
    """Patch lane-owner resolution so task potential owners stay tenant-aware."""
    global _PATCHED
    if _PATCHED:
        return

    from SpiffWorkflow.task import Task as SpiffTask  # type: ignore
    from spiffworkflow_backend.interfaces import PotentialOwnerIdList
    from spiffworkflow_backend.models.group import GroupModel
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
            explicit_lane_owners = _lane_owner_identifiers_for_task(task, task_lane)
            if explicit_lane_owners is not None:
                for username_or_email in explicit_lane_owners:
                    for lane_owner_user in find_users_for_current_tenant_by_identifier(username_or_email):
                        potential_owners.append(
                            {"added_by": HumanTaskUserAddedBy.lane_owner.value, "user_id": lane_owner_user.id}
                        )
                self.raise_if_no_potential_owners(
                    potential_owners,
                    (
                        "No users found in task data lane owner list for lane:"
                        f" {task_lane}. The user list used:"
                        f" {explicit_lane_owners}"
                    ),
                )
            else:
                group_model = None
                candidate_group_identifiers = _candidate_lane_group_identifiers(task_lane)
                for group_identifier in candidate_group_identifiers:
                    group_model = GroupModel.query.filter_by(identifier=group_identifier).first()
                    if group_model is not None:
                        break

                if group_model is None:
                    if not candidate_group_identifiers:
                        self.raise_if_no_potential_owners(
                            [],
                            f"No usable BPMN lane group identifier could be derived from lane: {task_lane}",
                        )
                    group_model = UserService.find_or_create_group(candidate_group_identifiers[0])

                lane_assignment_id = group_model.id
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
