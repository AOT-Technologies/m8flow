from __future__ import annotations

import importlib
import logging

_PATCHED = False
_logger = logging.getLogger(__name__)


def apply() -> None:
    """Patch _update_form_schema_with_task_data_as_needed to log warnings instead of raising 500 errors
    when task data variables referenced in form schemas are missing or empty lists."""
    global _PATCHED
    if _PATCHED:
        return

    process_api_blueprint = importlib.import_module("spiffworkflow_backend.routes.process_api_blueprint")
    from spiffworkflow_backend.exceptions.api_error import ApiError

    def _patched_update_form_schema_with_task_data_as_needed(in_dict: dict, task_data: dict) -> None:
        for k, value in in_dict.items():
            if k in {"anyOf", "items"}:
                if isinstance(value, list):
                    if len(value) == 1:
                        first_element_in_value_list = value[0]
                        if isinstance(first_element_in_value_list, str):
                            if first_element_in_value_list.startswith("options_from_task_data_var:"):
                                task_data_var = first_element_in_value_list.replace("options_from_task_data_var:", "")

                                if task_data_var not in task_data:
                                    _logger.warning(
                                        "Error building form. Attempting to create a selection list with options from"
                                        " variable '%s' but it doesn't exist in the Task Data."
                                        " Rendering form with empty options.",
                                        task_data_var,
                                    )
                                    in_dict[k] = []
                                    continue

                                select_options_from_task_data = task_data.get(task_data_var)
                                if select_options_from_task_data == []:
                                    _logger.warning(
                                        "This form depends on variables, but at least one variable was empty."
                                        " The variable '%s' is an empty list."
                                        " Rendering form with empty options.",
                                        task_data_var,
                                    )
                                    in_dict[k] = []
                                    continue
                                if isinstance(select_options_from_task_data, str):
                                    raise ApiError(
                                        error_code="invalid_form_data",
                                        message=(
                                            "This form depends on enum variables, but at least one variable was a string."
                                            f" The variable '{task_data_var}' must be a list with at least one element."
                                        ),
                                        status_code=400,
                                    )
                                if isinstance(select_options_from_task_data, list):
                                    if all("value" in d and "label" in d for d in select_options_from_task_data):

                                        def map_function(task_data_select_option: dict) -> dict:
                                            return {
                                                "type": "string",
                                                "enum": [task_data_select_option["value"]],
                                                "title": task_data_select_option["label"],
                                            }

                                        in_dict[k] = list(map(map_function, select_options_from_task_data))
                                    else:
                                        in_dict[k] = select_options_from_task_data
            elif isinstance(value, dict):
                _patched_update_form_schema_with_task_data_as_needed(value, task_data)
            elif isinstance(value, list):
                for o in value:
                    if isinstance(o, dict):
                        _patched_update_form_schema_with_task_data_as_needed(o, task_data)

    process_api_blueprint._update_form_schema_with_task_data_as_needed = (
        _patched_update_form_schema_with_task_data_as_needed
    )
    _PATCHED = True
