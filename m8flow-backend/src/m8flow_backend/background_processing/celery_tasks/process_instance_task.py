"""M8flow wrapper tasks for upstream SpiffWorkflow Celery tasks.

Each wrapper delegates to the upstream task's raw callable at runtime so we never
duplicate business logic.  The wrappers are registered under m8flow task names,
which keeps Flower UI and ``send_task()`` calls branded consistently.
"""

from __future__ import annotations

from contextvars import Token
from typing import Any

from celery import shared_task

from m8flow_backend.background_processing import (
    M8FLOW_CELERY_TASK_EVENT_NOTIFIER,
    M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN,
)
from m8flow_backend.services.celery_worker_runtime import cleanup_scoped_session
from m8flow_backend.services.celery_worker_runtime import tenant_id_for_process_instance
from m8flow_backend.services.celery_tenant_context_patch import TENANT_HEADER_NAME
from m8flow_backend.tenancy import reset_context_tenant_id
from m8flow_backend.tenancy import set_context_tenant_id
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task import (
    TEN_MINUTES,
)
from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task import (
    celery_task_process_instance_run as _upstream_process_instance_run,
)
from spiffworkflow_backend.background_processing.celery_tasks.process_instance_task import (
    celery_task_event_notifier_run as _upstream_event_notifier_run,
)


def _task_tenant_id(self: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    request = getattr(self, "request", None)
    headers = getattr(request, "headers", None)
    if isinstance(headers, dict):
        header_tenant = headers.get(TENANT_HEADER_NAME)
        if isinstance(header_tenant, str) and header_tenant:
            return header_tenant

    process_instance_id = kwargs.get("process_instance_id")
    if process_instance_id is None and args:
        process_instance_id = args[0]

    if isinstance(process_instance_id, str) and process_instance_id.isdigit():
        process_instance_id = int(process_instance_id)

    if isinstance(process_instance_id, int):
        return tenant_id_for_process_instance(db.engine, process_instance_id)
    return None


def _begin_task(self: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Token | None:
    cleanup_scoped_session(db.session)

    tenant_id = _task_tenant_id(self, args, kwargs)
    if tenant_id:
        return set_context_tenant_id(tenant_id)
    return None


def _end_task(token: Token | None) -> None:
    cleanup_scoped_session(db.session)
    if token is not None:
        reset_context_tenant_id(token)


@shared_task(name=M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN, bind=True, ignore_result=False, time_limit=TEN_MINUTES)
def celery_task_process_instance_run(self: Any, *args: Any, **kwargs: Any) -> dict:  # type: ignore[type-arg]
    token = _begin_task(self, args, kwargs)
    try:
        return _upstream_process_instance_run.run(*args, **kwargs)
    finally:
        _end_task(token)


@shared_task(name=M8FLOW_CELERY_TASK_EVENT_NOTIFIER, bind=True, ignore_result=False, time_limit=TEN_MINUTES)
def celery_task_event_notifier_run(self: Any, *args: Any, **kwargs: Any) -> dict:  # type: ignore[type-arg]
    token = _begin_task(self, args, kwargs)
    try:
        return _upstream_event_notifier_run.run(*args, **kwargs)
    finally:
        _end_task(token)
