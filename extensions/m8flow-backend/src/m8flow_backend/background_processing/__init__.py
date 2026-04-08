"""Background processing entrypoints for m8flow extension runtime.

Celery task names shown in Flower default to the fully-qualified Python module path.
Upstream tasks live under ``spiffworkflow_backend.*``; to present m8flow branding in the
Celery UI without modifying upstream code, we rebrand task names at runtime after the
Celery app has been initialized and tasks have been registered.
"""

from __future__ import annotations

import importlib
from collections import Counter
from typing import Any

_NEW_PREFIX = "m8flow_backend"

M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN = (
    "m8flow_backend.background_processing.celery_tasks.process_instance_task.celery_task_process_instance_run"
)
M8FLOW_CELERY_TASK_EVENT_NOTIFIER = (
    "m8flow_backend.background_processing.celery_tasks.process_instance_task.celery_task_event_notifier_run"
)


def _detect_old_prefix(flask_app: Any, celery_app: Any) -> str | None:
    keys = list(getattr(celery_app, "tasks", {}).keys())
    candidate_prefixes: list[str] = []

    marker = ".background_processing.celery_tasks."
    for name in keys:
        if not isinstance(name, str):
            continue
        if name.startswith("celery."):
            continue
        idx = name.find(marker)
        if idx > 0:
            candidate_prefixes.append(name[:idx])

    if candidate_prefixes:
        return Counter(candidate_prefixes).most_common(1)[0][0]

    main = getattr(celery_app, "main", None)
    if isinstance(main, str) and main and main != _NEW_PREFIX:
        return main

    app_name = getattr(flask_app, "name", None)
    if isinstance(app_name, str) and app_name and app_name != _NEW_PREFIX:
        return app_name

    return None


def _iter_tasks_to_rebrand(celery_app: Any, old_prefix: str) -> list[tuple[str, str]]:
    keys = list(getattr(celery_app, "tasks", {}).keys())
    return [
        (old, old.replace(old_prefix, _NEW_PREFIX, 1))
        for old in keys
        if isinstance(old, str) and old.startswith(old_prefix) and not old.startswith("celery.")
    ]


def rebrand_celery_tasks(flask_app: Any) -> None:
    """Rename upstream SpiffWorkflow Celery tasks to m8flow names.

    Must be called after upstream app initialization has created and configured the Celery app.
    Safe to call multiple times.
    """

    celery_app = getattr(flask_app, "celery_app", None)
    if celery_app is None:
        return

    old_prefix = _detect_old_prefix(flask_app, celery_app)
    if old_prefix is None or old_prefix == _NEW_PREFIX:
        celery_app.main = _NEW_PREFIX
        return

    celery_app.main = _NEW_PREFIX

    tasks_to_rename = _iter_tasks_to_rebrand(celery_app, old_prefix)
    for old_name, new_name in tasks_to_rename:
        if new_name in celery_app.tasks:
            continue
        task = celery_app.tasks.pop(old_name, None)
        if task is None:
            continue
        try:
            task.name = new_name
        except Exception:
            # Some task objects may not allow setting name; skip those.
            celery_app.tasks[old_name] = task
            continue
        # Prefer the Celery TaskRegistry API when available.
        if hasattr(celery_app.tasks, "register"):
            try:
                celery_app.tasks.register(task)  # type: ignore[attr-defined]
                continue
            except Exception:
                pass
        celery_app.tasks[new_name] = task

    # Patch upstream constants so send_task() dispatches with new names.
    # This avoids any changes in spiffworkflow-backend while keeping worker + UI consistent.
    try:
        bg_mod = importlib.import_module(f"{old_prefix}.background_processing")
        producer_mod = importlib.import_module(
            f"{old_prefix}.background_processing.celery_tasks.process_instance_task_producer"
        )

        setattr(bg_mod, "CELERY_TASK_PROCESS_INSTANCE_RUN", M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN)
        setattr(bg_mod, "CELERY_TASK_EVENT_NOTIFIER", M8FLOW_CELERY_TASK_EVENT_NOTIFIER)
        setattr(producer_mod, "CELERY_TASK_PROCESS_INSTANCE_RUN", M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN)
        setattr(producer_mod, "CELERY_TASK_EVENT_NOTIFIER", M8FLOW_CELERY_TASK_EVENT_NOTIFIER)
    except Exception:
        # If upstream modules aren't importable in this runtime, do nothing.
        return

