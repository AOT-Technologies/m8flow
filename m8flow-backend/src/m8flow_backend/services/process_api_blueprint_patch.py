from __future__ import annotations

import importlib
import logging

_PATCHED = False
_logger = logging.getLogger(__name__)

# Modules that import _get_task_model_for_request by name and therefore need rebinding.
_GET_TASK_MODEL_CALLER_MODULES = (
    "spiffworkflow_backend.routes.process_api_blueprint",
    "spiffworkflow_backend.routes.tasks_controller",
    "spiffworkflow_backend.routes.public_controller",
)


def _make_external_form_aware_get_task_model(original, api_error_cls):
    """Wrap _get_task_model_for_request so a user task configured with an external form
    (spiffworkflow:property externalFormUrl) no longer 500s on the missing local form file.

    Upstream requires every UserTask to have a formJsonSchemaFilename. External-form tasks
    intentionally have none, so we catch only that specific error and, when the task carries
    an externalFormUrl, return the task without a local form schema (with_form_data=False
    skips the form-building block entirely). Any other task still raises as before.

    Because that block is skipped, the form-related attributes the task page expects are
    never set. We populate safe empties so the upstream TaskShow renders instead of crashing
    on `'ui:submitButtonOptions' in form_ui_schema` / `signal_buttons.map(...)` (and hanging
    when `data` is absent), and we set instructionsForEndUser to a short note explaining the
    task is completed via an emailed link (no in-app link — the bare URL has no recipient
    token and the task must not be completable here).
    NOTE: this is a fallback — the in-app form is empty; rendering/redirecting to the external
    form itself is handled elsewhere."""

    def _patched_get_task_model_for_request(process_instance_id, task_guid="next", with_form_data=False):
        try:
            return original(process_instance_id, task_guid=task_guid, with_form_data=with_form_data)
        except api_error_cls as exc:
            if getattr(exc, "error_code", None) != "missing_form_file":
                raise
            task_model = original(process_instance_id, task_guid=task_guid, with_form_data=False)
            properties = (getattr(task_model, "extensions", None) or {}).get("properties", {})
            external_form_url = properties.get("externalFormUrl")
            if not external_form_url:
                raise
            _logger.info(
                "Task %s (process instance %s) uses an external form (%s); "
                "returning task without a local form schema.",
                task_guid,
                process_instance_id,
                external_form_url,
            )
            if with_form_data:
                task_model.form_schema = {}
                task_model.form_ui_schema = {}
                task_model.data = task_model.get_data()
                task_model.saved_form_data = None
                task_model.signal_buttons = []
                extensions = getattr(task_model, "extensions", None)
                if isinstance(extensions, dict):
                    # Deliberately no link: the in-app task page must not offer a way to open
                    # the form. Each recipient is emailed their own secure link (with a unique
                    # ref= token); the bare externalFormUrl here carries no token and the task
                    # stays open until the recipient submits via that emailed link.
                    extensions["instructionsForEndUser"] = (
                        "This task is completed using an external form. The assigned "
                        "recipient receives a secure link by email and cannot complete it here."
                    )
            return task_model

    return _patched_get_task_model_for_request


_TASK_DATA_VAR_PREFIX = "options_from_task_data_var:"


def _task_data_var_name(anyof_or_items_value: object) -> str | None:
    """A dynamic option list is encoded as a one-element list holding the string
    ``options_from_task_data_var:<name>``. Return ``<name>`` for that shape, else None."""
    if not (isinstance(anyof_or_items_value, list) and len(anyof_or_items_value) == 1):
        return None
    sole = anyof_or_items_value[0]
    if isinstance(sole, str) and sole.startswith(_TASK_DATA_VAR_PREFIX):
        return sole[len(_TASK_DATA_VAR_PREFIX):]
    return None


def _resolve_task_data_option_list(container: dict, key: str, task_data: dict) -> None:
    """Replace a ``anyOf``/``items`` placeholder with the concrete options resolved from
    ``task_data``. m8flow's divergence from upstream: a missing or empty source variable
    renders an empty option set (with a warning) instead of raising a 500; a string source
    is a 400 (client) rather than a 500."""
    from spiffworkflow_backend.exceptions.api_error import ApiError

    var_name = _task_data_var_name(container[key])
    if var_name is None:
        return

    if var_name not in task_data:
        _logger.warning(
            "Form option variable '%s' is not in the task data; rendering empty options.",
            var_name,
        )
        container[key] = []
        return

    source = task_data.get(var_name)
    if source == []:
        _logger.warning(
            "Form option variable '%s' is an empty list; rendering empty options.",
            var_name,
        )
        container[key] = []
        return
    if isinstance(source, str):
        raise ApiError(
            error_code="invalid_form_data",
            message=(
                "This form depends on enum variables, but at least one variable was a string."
                f" The variable '{var_name}' must be a list with at least one element."
            ),
            status_code=400,
        )
    if not isinstance(source, list):
        return

    if all(isinstance(o, dict) and "value" in o and "label" in o for o in source):
        container[key] = [
            {"type": "string", "enum": [option["value"]], "title": option["label"]}
            for option in source
        ]
    else:
        container[key] = source


def _patched_update_form_schema_with_task_data_as_needed(in_dict: dict, task_data: dict) -> None:
    """m8flow form-schema builder: resolve dynamic option lists, recursing through nested
    schema dicts/lists. Re-expressed independently of upstream (guard clauses + helpers)."""
    for key, value in in_dict.items():
        if key in {"anyOf", "items"}:
            _resolve_task_data_option_list(in_dict, key, task_data)
        elif isinstance(value, dict):
            _patched_update_form_schema_with_task_data_as_needed(value, task_data)
        elif isinstance(value, list):
            for element in value:
                if isinstance(element, dict):
                    _patched_update_form_schema_with_task_data_as_needed(element, task_data)


def apply() -> None:
    """Patches for spiffworkflow_backend.routes.process_api_blueprint:

    1. _update_form_schema_with_task_data_as_needed logs warnings instead of raising 500s
       when task-data variables referenced in form schemas are missing or empty lists.
    2. _get_task_model_for_request returns external-form user tasks without a local form
       instead of raising missing_form_file (see _make_external_form_aware_get_task_model)."""
    global _PATCHED
    if _PATCHED:
        return

    process_api_blueprint = importlib.import_module("spiffworkflow_backend.routes.process_api_blueprint")
    from spiffworkflow_backend.exceptions.api_error import ApiError

    process_api_blueprint._update_form_schema_with_task_data_as_needed = (
        _patched_update_form_schema_with_task_data_as_needed
    )

    # Rebind _get_task_model_for_request everywhere it is referenced. The route modules
    # import it by name (from ... import ...), so patching only the source module would
    # not reach them.
    patched_get_task_model = _make_external_form_aware_get_task_model(
        process_api_blueprint._get_task_model_for_request, ApiError
    )
    for module_name in _GET_TASK_MODEL_CALLER_MODULES:
        module = importlib.import_module(module_name)
        if hasattr(module, "_get_task_model_for_request"):
            module._get_task_model_for_request = patched_get_task_model

    _PATCHED = True
