"""M8flow Celery task registration."""

from __future__ import annotations

from typing import Any

from m8flow_backend.background_processing.celery_tasks.process_instance_task import (
    celery_task_event_notifier_run,
    celery_task_process_instance_run,
)

__all__ = [
    "celery_task_process_instance_run",
    "celery_task_event_notifier_run",
    "register",
]


def register(celery_app: Any) -> None:
    """Register m8flow wrapper tasks onto *celery_app*.

    Safe to call multiple times -- skips tasks that are already present.
    """
    for task in (celery_task_process_instance_run, celery_task_event_notifier_run):
        if task.name in celery_app.tasks:
            continue
        if hasattr(celery_app.tasks, "register"):
            celery_app.tasks.register(task)
        else:
            celery_app.tasks[task.name] = task
