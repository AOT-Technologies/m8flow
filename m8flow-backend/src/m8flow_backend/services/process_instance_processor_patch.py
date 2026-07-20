from __future__ import annotations

import re
from collections.abc import Mapping

from flask import current_app

from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_identifier
from m8flow_backend.services.tenant_identity_helpers import normalize_organizational_group_identifier
from m8flow_backend.services.tenant_identity_helpers import qualify_group_identifier
from m8flow_backend.services.tenant_identity_helpers import realm_from_service

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
        task_lane.strip().strip("/").split("/")[-1].strip(),
        normalize_organizational_group_identifier(task_lane),
    ):
        if not raw_identifier:
            continue
        qualified_identifier = qualify_group_identifier(raw_identifier)
        if qualified_identifier and qualified_identifier not in seen:
            seen.add(qualified_identifier)
            candidates.append(qualified_identifier)

    return candidates


def _user_recency_key(user: object) -> tuple[int, int, int]:
    """Sort users by most recently updated, then created, then id."""
    return (
        int(getattr(user, "updated_at_in_seconds", 0) or 0),
        int(getattr(user, "created_at_in_seconds", 0) or 0),
        int(getattr(user, "id", 0) or 0),
    )


def _shared_realm_service_issuer() -> str | None:
    """Return the configured shared-realm issuer URL used for local user rows."""
    try:
        from m8flow_backend.config import keycloak_url
        from m8flow_backend.config import shared_realm_name

        return f"{keycloak_url().rstrip('/')}/realms/{shared_realm_name().strip()}"
    except Exception:
        return None


def _materialize_lane_owner_users_for_identifier(
    username_or_email: str,
    *,
    user_model_cls: object,
    user_service_cls: object,
) -> list[object]:
    """
    Resolve explicit lane owners for the current tenant, creating a placeholder when needed.

    Explicit lane-owner assignments are per-user, not per-group. When a valid shared-realm
    user has not been mirrored into the local DB yet, keep the task bound to that username by
    creating or reusing a shared-realm local placeholder row instead of broadening ownership to
    the lane group.
    """
    normalized_identifier = username_or_email.strip()
    if not normalized_identifier:
        return []

    tenant_matches = find_users_for_current_tenant_by_identifier(normalized_identifier)
    if tenant_matches:
        return tenant_matches

    shared_realm_service = _shared_realm_service_issuer()
    if not shared_realm_service:
        return []

    shared_realm = realm_from_service(shared_realm_service)
    same_username_matches = user_model_cls.query.filter_by(username=normalized_identifier).all()
    same_realm_matches = [
        user for user in same_username_matches if realm_from_service(getattr(user, "service", None)) == shared_realm
    ]
    if same_realm_matches:
        same_realm_matches.sort(key=_user_recency_key, reverse=True)
        if len(same_realm_matches) > 1:
            current_app.logger.warning(
                "lane_owner_placeholder_match: found %s local shared-realm users for username=%s; reusing id=%s",
                len(same_realm_matches),
                normalized_identifier,
                getattr(same_realm_matches[0], "id", None),
            )
        return [same_realm_matches[0]]

    placeholder_service_id = f"lane-owner-placeholder:{normalized_identifier}"
    try:
        created_user = user_service_cls.create_user(
            normalized_identifier,
            shared_realm_service,
            placeholder_service_id,
            email="",
            display_name=normalized_identifier,
        )
    except Exception:
        fallback_matches = user_model_cls.query.filter_by(username=normalized_identifier).all()
        fallback_same_realm_matches = [
            user for user in fallback_matches if realm_from_service(getattr(user, "service", None)) == shared_realm
        ]
        if not fallback_same_realm_matches:
            return []
        fallback_same_realm_matches.sort(key=_user_recency_key, reverse=True)
        current_app.logger.warning(
            "lane_owner_placeholder_fallback: reusing username=%s after create_user failure",
            normalized_identifier,
        )
        return [fallback_same_realm_matches[0]]

    if created_user is None:
        return []
    return [created_user]


def _lane_assignment_for_task_lane(
    task_lane: str,
    *,
    group_model_cls: object,
    user_service_cls: object,
    human_task_user_added_by: object,
    processor: object,
) -> tuple[list[dict[str, object]], int | None]:
    """Resolve the tenant-scoped lane group and its current members for one BPMN lane."""
    group_model = None
    fallback_group_model = None
    candidate_group_identifiers = _candidate_lane_group_identifiers(task_lane)
    for group_identifier in candidate_group_identifiers:
        candidate_group_model = group_model_cls.query.filter_by(identifier=group_identifier).first()
        if candidate_group_model is None:
            continue

        if fallback_group_model is None:
            fallback_group_model = candidate_group_model

        if getattr(candidate_group_model, "user_group_assignments", []):
            group_model = candidate_group_model
            break

    if group_model is None:
        group_model = fallback_group_model

    if group_model is None:
        if not candidate_group_identifiers:
            processor.raise_if_no_potential_owners(
                [],
                f"No usable BPMN lane group identifier could be derived from lane: {task_lane}",
            )
            return [], None
        group_model = user_service_cls.find_or_create_group(candidate_group_identifiers[0])

    lane_assignment_id = group_model.id
    potential_owners = [
        {"added_by": human_task_user_added_by.lane_assignment.value, "user_id": assignment.user_id}
        for assignment in group_model.user_group_assignments
    ]
    return potential_owners, lane_assignment_id


def apply() -> None:
    """Patch lane-owner resolution so task potential owners stay tenant-aware."""
    global _PATCHED
    if _PATCHED:
        return

    from SpiffWorkflow.task import Task as SpiffTask  # type: ignore
    from spiffworkflow_backend.interfaces import PotentialOwnerIdList
    from spiffworkflow_backend.models.group import GroupModel
    from spiffworkflow_backend.models.human_task_user import HumanTaskUserAddedBy
    from spiffworkflow_backend.models.user import UserModel
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
                seen_user_ids: set[object] = set()
                for username_or_email in explicit_lane_owners:
                    for lane_owner_user in _materialize_lane_owner_users_for_identifier(
                        username_or_email,
                        user_model_cls=UserModel,
                        user_service_cls=UserService,
                    ):
                        user_id = getattr(lane_owner_user, "id", None)
                        if user_id in seen_user_ids:
                            continue
                        seen_user_ids.add(user_id)
                        potential_owners.append(
                            {"added_by": HumanTaskUserAddedBy.lane_owner.value, "user_id": user_id}
                        )
                self.raise_if_no_potential_owners(
                    potential_owners,
                    (
                        "No users found in task data lane owner list for lane:"
                        f" {task_lane}. The user list used:"
                        f" {explicit_lane_owners}"
                    ),
                )
                return {
                    "potential_owners": potential_owners,
                    "lane_assignment_id": None,
                }
            else:
                potential_owners, lane_assignment_id = _lane_assignment_for_task_lane(
                    task_lane,
                    group_model_cls=GroupModel,
                    user_service_cls=UserService,
                    human_task_user_added_by=HumanTaskUserAddedBy,
                    processor=self,
                )

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
