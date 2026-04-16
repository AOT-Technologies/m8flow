from __future__ import annotations

import flask.wrappers
from flask import jsonify
from flask import make_response

from m8flow_backend.services.tenant_identity_helpers import display_group_identifier

_PATCHED = False


def _rewrite_assigned_group_identifiers(response: flask.wrappers.Response) -> flask.wrappers.Response:
    """Rewrite raw tenant-qualified group identifiers in task-list payloads for display."""
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict):
        return response

    results = payload.get("results")
    if not isinstance(results, list):
        return response

    for result in results:
        if not isinstance(result, dict):
            continue
        assigned_user_group_identifier = result.get("assigned_user_group_identifier")
        if isinstance(assigned_user_group_identifier, str):
            result["assigned_user_group_identifier"] = display_group_identifier(assigned_user_group_identifier)

    return make_response(jsonify(payload), response.status_code)


def apply() -> None:
    """Patch task-list endpoints so waiting-for group labels are tenant-slug based."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.routes import tasks_controller

    original_get_tasks = tasks_controller._get_tasks
    original_task_list_my_tasks = tasks_controller.task_list_my_tasks

    def patched_get_tasks(*args, **kwargs) -> flask.wrappers.Response:
        return _rewrite_assigned_group_identifiers(original_get_tasks(*args, **kwargs))

    def patched_task_list_my_tasks(*args, **kwargs) -> flask.wrappers.Response:
        return _rewrite_assigned_group_identifiers(original_task_list_my_tasks(*args, **kwargs))

    tasks_controller._get_tasks = patched_get_tasks
    tasks_controller.task_list_my_tasks = patched_task_list_my_tasks
    _PATCHED = True
