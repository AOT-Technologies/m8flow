"""M8flow wrapper tasks for upstream SpiffWorkflow Celery tasks.

Each wrapper delegates to the upstream task's raw callable at runtime so we never
duplicate business logic.  The wrappers are registered under m8flow task names,
which keeps Flower UI and ``send_task()`` calls branded consistently.
"""

from __future__ import annotations

from typing import Any

from celery import shared_task

from m8flow_backend.background_processing import (
    M8FLOW_CELERY_TASK_EVENT_NOTIFIER,
    M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN,
)
from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task import (
    TEN_MINUTES,
)
from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task import (
    celery_task_process_instance_run as _upstream_process_instance_run,
)
from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task import (
    celery_task_event_notifier_run as _upstream_event_notifier_run,
)


@shared_task(name=M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN, bind=True, ignore_result=False, time_limit=TEN_MINUTES)
def celery_task_process_instance_run(self: Any, *args: Any, **kwargs: Any) -> dict:  # type: ignore[type-arg]
    return _upstream_process_instance_run.run(*args, **kwargs)


@shared_task(name=M8FLOW_CELERY_TASK_EVENT_NOTIFIER, bind=True, ignore_result=False, time_limit=TEN_MINUTES)
def celery_task_event_notifier_run(self: Any, *args: Any, **kwargs: Any) -> dict:  # type: ignore[type-arg]
    return _upstream_event_notifier_run.run(*args, **kwargs)
