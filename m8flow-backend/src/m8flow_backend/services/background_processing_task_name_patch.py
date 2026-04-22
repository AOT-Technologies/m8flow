"""Post-app patch that registers m8flow Celery wrapper tasks and rebinds upstream constants.

Must run after the Flask app and its Celery app exist.  Registered in
``extensions.startup.patch_registry`` with ``needs_flask_app=True``.
"""

from __future__ import annotations

import importlib
from typing import Any

from m8flow_backend.background_processing import (
    M8FLOW_CELERY_TASK_EVENT_NOTIFIER,
    M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN,
)


def apply(flask_app: Any) -> None:
    celery_app = getattr(flask_app, "celery_app", None)
    if celery_app is None:
        return

    # Ensure the upstream task module is imported so legacy task registrations exist.
    importlib.import_module(
        "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task"
    )

    # Register the m8flow wrapper tasks onto the same Celery app.
    from m8flow_backend.background_processing.celery_tasks import register

    register(celery_app)

    # Rebind task-name constants in upstream modules so future send_task() calls
    # dispatch under m8flow names.
    try:
        bg_mod = importlib.import_module("spiffworkflow_backend.background_processing")
        producer_mod = importlib.import_module(
            "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task_producer"
        )

        bg_mod.CELERY_TASK_PROCESS_INSTANCE_RUN = M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN  # type: ignore[attr-defined]
        bg_mod.CELERY_TASK_EVENT_NOTIFIER = M8FLOW_CELERY_TASK_EVENT_NOTIFIER  # type: ignore[attr-defined]
        producer_mod.CELERY_TASK_PROCESS_INSTANCE_RUN = M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN  # type: ignore[attr-defined]
        producer_mod.CELERY_TASK_EVENT_NOTIFIER = M8FLOW_CELERY_TASK_EVENT_NOTIFIER  # type: ignore[attr-defined]
    except Exception:
        pass
