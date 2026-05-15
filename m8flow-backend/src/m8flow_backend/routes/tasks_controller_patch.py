from __future__ import annotations

import flask.wrappers
from flask import current_app
from flask import jsonify
from flask import make_response

from m8flow_backend.services.tenant_identity_helpers import display_group_identifier

_MODULE_PATCHED = False
_ORIGINAL_TASK_DATA_SHOW: object | None = None


def _task_data_for_display(task_model: object) -> dict:
    task_data = task_model.get_data()
    if isinstance(task_data, dict) and task_data:
        return task_data

    # Completed user tasks keep submitted fields in the serialized delta, not the task-data hashes.
    properties_json = getattr(task_model, "properties_json", None)
    if not isinstance(properties_json, dict):
        return task_data if isinstance(task_data, dict) else {}

    delta = properties_json.get("delta")
    if not isinstance(delta, dict):
        return task_data if isinstance(task_data, dict) else {}

    delta_updates = delta.get("updates")
    if not isinstance(delta_updates, dict) or not delta_updates:
        return task_data if isinstance(task_data, dict) else {}

    if isinstance(task_data, dict):
        return {**task_data, **delta_updates}
    return delta_updates


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


def _rule_looks_like_task_data_show(rule: object) -> bool:
    rule_path = getattr(rule, "rule", None)
    if not isinstance(rule_path, str):
        return False
    return "task-data" in rule_path and "task_guid" in rule_path and "process_instance_id" in rule_path


def _apply_module_patches():
    import importlib

    tasks_controller = importlib.import_module("spiffworkflow_backend.routes.tasks_controller")
    global _MODULE_PATCHED
    global _ORIGINAL_TASK_DATA_SHOW
    if _MODULE_PATCHED:
        return tasks_controller, _ORIGINAL_TASK_DATA_SHOW, getattr(tasks_controller, "task_data_show", None)

    original_get_tasks = tasks_controller._get_tasks
    original_task_list_my_tasks = tasks_controller.task_list_my_tasks
    _ORIGINAL_TASK_DATA_SHOW = getattr(tasks_controller, "task_data_show", None)

    def patched_get_tasks(*args, **kwargs) -> flask.wrappers.Response:
        return _rewrite_assigned_group_identifiers(original_get_tasks(*args, **kwargs))

    def patched_task_list_my_tasks(*args, **kwargs) -> flask.wrappers.Response:
        return _rewrite_assigned_group_identifiers(original_task_list_my_tasks(*args, **kwargs))

    def patched_task_data_show(
        modified_process_model_identifier: str,
        process_instance_id: int,
        task_guid: str,
    ) -> flask.wrappers.Response:
        task_model = tasks_controller._get_task_model_from_guid_or_raise(task_guid, process_instance_id)
        task_model.data = _task_data_for_display(task_model)
        return make_response(jsonify(task_model), 200)

    tasks_controller._get_tasks = patched_get_tasks
    tasks_controller.task_list_my_tasks = patched_task_list_my_tasks
    tasks_controller.task_data_show = patched_task_data_show
    _MODULE_PATCHED = True
    return tasks_controller, _ORIGINAL_TASK_DATA_SHOW, patched_task_data_show


def apply(flask_app: object | None = None) -> None:
    """Patch task endpoints so waiting-for group labels and task data display are m8flow-aware."""
    tasks_controller, original_task_data_show, patched_task_data_show = _apply_module_patches()

    if flask_app is None:
        try:
            flask_app = current_app._get_current_object()
        except RuntimeError:
            return

    app_already_patched = getattr(flask_app, "_m8flow_tasks_controller_patch_applied", False)
    if app_already_patched:
        return

    for endpoint, view_function in list(flask_app.view_functions.items()):
        if endpoint.endswith("task_data_show") or (
            getattr(view_function, "__module__", None) == tasks_controller.__name__
            and getattr(view_function, "__name__", None) == "task_data_show"
        ):
            flask_app.view_functions[endpoint] = patched_task_data_show

    # Connexion endpoint names and wrapper identities vary between environments.
    # First try function identity, then fall back to the concrete task-data route path.
    for rule in flask_app.url_map.iter_rules():
        if "GET" not in rule.methods:
            continue
        vf = flask_app.view_functions.get(rule.endpoint)
        if original_task_data_show is not None and getattr(vf, "__wrapped__", vf) is original_task_data_show:
            flask_app.view_functions[rule.endpoint] = patched_task_data_show
            continue
        if _rule_looks_like_task_data_show(rule):
            flask_app.view_functions[rule.endpoint] = patched_task_data_show

    setattr(flask_app, "_m8flow_tasks_controller_patch_applied", True)
