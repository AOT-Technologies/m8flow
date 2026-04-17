from __future__ import annotations

import re

from flask import current_app

from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_identifier

_PATCHED = False


def apply() -> None:
    """Patch lane-owner resolution so task potential owners stay tenant-aware."""
    global _PATCHED
    if _PATCHED:
        return

    from SpiffWorkflow.task import Task as SpiffTask  # type: ignore
    from spiffworkflow_backend.interfaces import PotentialOwnerIdList
    from spiffworkflow_backend.models.human_task_user import HumanTaskUserAddedBy
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
            if "lane_owners" in task.data and task_lane in task.data["lane_owners"]:
                for username_or_email in task.data["lane_owners"][task_lane]:
                    for lane_owner_user in find_users_for_current_tenant_by_identifier(username_or_email):
                        potential_owners.append(
                            {"added_by": HumanTaskUserAddedBy.lane_owner.value, "user_id": lane_owner_user.id}
                        )
                self.raise_if_no_potential_owners(
                    potential_owners,
                    (
                        "No users found in task data lane owner list for lane:"
                        f" {task_lane}. The user list used:"
                        f" {task.data['lane_owners'][task_lane]}"
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

    ProcessInstanceProcessor.get_potential_owners_from_task = patched_get_potential_owners_from_task
    _PATCHED = True
