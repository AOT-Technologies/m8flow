from __future__ import annotations

import importlib
import logging

from flask import g

from spiffworkflow_backend.exceptions.api_error import ApiError

_PATCHED = False
_logger = logging.getLogger("m8flow.external_forms.completion_guard")

# Flag ExternalFormService.submit() sets on the request so the external-form submission
# is the ONLY path allowed to complete a user task that carries externalFormUrl. Any
# other route (in-app task page, guest/public controller) is rejected — the task waits
# for the external form.
EXTERNAL_FORM_COMPLETION_FLAG = "_m8flow_external_form_completion"

# Modules that import _task_submit_shared by name and therefore need rebinding (mirrors
# the _get_task_model_for_request rebinding in process_api_blueprint_patch).
_TASK_SUBMIT_CALLER_MODULES = (
    "spiffworkflow_backend.routes.process_api_blueprint",
    "spiffworkflow_backend.routes.tasks_controller",
    "spiffworkflow_backend.routes.public_controller",
)


def _external_form_completion_allowed() -> bool:
    """True only when the external-form submission set the allow-flag on this request."""
    try:
        return bool(getattr(g, EXTERNAL_FORM_COMPLETION_FLAG, False))
    except Exception:
        # No request/app context (e.g. background processing) — never the external path.
        return False


def task_has_external_form_url(task_guid: str) -> bool:
    """Whether the task definition for this guid carries the externalFormUrl extension."""
    from spiffworkflow_backend.models.task import TaskModel

    task_model = TaskModel.query.filter_by(guid=str(task_guid)).first()
    task_definition = getattr(task_model, "task_definition", None) if task_model is not None else None
    properties_json = getattr(task_definition, "properties_json", None) or {}
    extensions = properties_json.get("extensions") or {}
    properties = extensions.get("properties") or {}
    return bool(properties.get("externalFormUrl"))


def assert_task_completable_in_app(task_guid: str) -> None:
    """Reject completing an external-form task by any route other than its external form."""
    if _external_form_completion_allowed():
        return
    try:
        is_external_form = task_has_external_form_url(task_guid)
    except Exception:
        # Fail open: a lookup error must not block normal task completion.
        _logger.warning("external-form guard: could not inspect task %s; allowing", task_guid, exc_info=True)
        return
    if is_external_form:
        _logger.info("external-form guard: blocked in-app completion of external-form task %s", task_guid)
        raise ApiError(
            error_code="external_form_task_not_completable_in_app",
            message=(
                "This task is completed through its external form and cannot be completed here. "
                "It stays open until the recipient submits the secure link."
            ),
            status_code=409,
        )


def apply() -> None:
    """Gate _task_submit_shared so external-form user tasks can only be completed via the
    external-form submission (M8F-339/340). The task waits — no in-app manual completion."""
    global _PATCHED
    if _PATCHED:
        return

    process_api_blueprint = importlib.import_module("spiffworkflow_backend.routes.process_api_blueprint")
    original = process_api_blueprint._task_submit_shared

    def guarded_task_submit_shared(process_instance_id, task_guid, body, execution_mode=None):
        assert_task_completable_in_app(task_guid)
        return original(process_instance_id, task_guid, body, execution_mode=execution_mode)

    # Preserve a handle so the external-form service (and tests) can reach the raw function.
    guarded_task_submit_shared.__wrapped__ = original  # type: ignore[attr-defined]

    for module_name in _TASK_SUBMIT_CALLER_MODULES:
        module = importlib.import_module(module_name)
        if hasattr(module, "_task_submit_shared"):
            module._task_submit_shared = guarded_task_submit_shared

    _PATCHED = True
