from __future__ import annotations

import logging
import sys
from contextvars import Token
from typing import Any

import celery
from sqlalchemy import text

from extensions.app import app as m8flow_app
from m8flow_backend.background_processing import M8FLOW_CELERY_TASK_EVENT_NOTIFIER as CELERY_TASK_EVENT_NOTIFIER
from m8flow_backend.background_processing import (
    M8FLOW_CELERY_TASK_PROCESS_INSTANCE_RUN as CELERY_TASK_PROCESS_INSTANCE_RUN,
)
from m8flow_backend.services.celery_tenant_context_patch import TENANT_HEADER_NAME
from m8flow_backend.tenancy import reset_context_tenant_id
from m8flow_backend.tenancy import set_context_tenant_id
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.services.logging_service import get_log_formatter
from spiffworkflow_backend.services.logging_service import setup_logger_for_app

_ACCEPTED_TASK_NAMES: frozenset[str] = frozenset({
    CELERY_TASK_PROCESS_INSTANCE_RUN,
    CELERY_TASK_EVENT_NOTIFIER,
    # Hard-coded legacy upstream names so already-queued jobs still resolve tenant context.
    # Do NOT import these from upstream — startup rebinding may have already replaced them.
    "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task.celery_task_process_instance_run",
    "spiffworkflow_backend.background_processing.celery_tasks.process_instance_task.celery_task_event_notifier_run",
})

_TASK_TENANT_TOKENS: dict[str, Token] = {}


def _resolve_connexion_app(app_obj: Any) -> Any:
    """Unwrap middleware wrappers and return the Connexion app instance."""
    current = app_obj
    visited_ids: set[int] = set()

    while current is not None:
        current_id = id(current)
        if current_id in visited_ids:
            break
        visited_ids.add(current_id)

        flask_app = getattr(current, "app", None)
        if flask_app is not None and hasattr(flask_app, "app_context"):
            return current

        current = getattr(current, "app", None)

    raise RuntimeError("Could not resolve Connexion app from m8flow application bootstrap.")


connexion_app = _resolve_connexion_app(m8flow_app)
the_flask_app = connexion_app.app
celery_app = getattr(the_flask_app, "celery_app", None)

if celery_app is None:
    raise RuntimeError(
        "Celery app was not initialized. "
        "Set M8FLOW_BACKEND_CELERY_ENABLED=true."
    )


def _extract_process_instance_id(task_name: str, args: Any, kwargs: Any) -> int | None:
    if task_name not in _ACCEPTED_TASK_NAMES:
        return None

    if isinstance(kwargs, dict):
        pid = kwargs.get("process_instance_id")
        if isinstance(pid, int):
            return pid
        if isinstance(pid, str) and pid.isdigit():
            return int(pid)

    if isinstance(args, (list, tuple)) and args:
        first = args[0]
        if isinstance(first, int):
            return first
        if isinstance(first, str) and first.isdigit():
            return int(first)

    return None


def _tenant_id_for_process_instance(process_instance_id: int) -> str | None:
    tenant_id = db.session.execute(
        text("SELECT m8f_tenant_id FROM process_instance WHERE id = :process_instance_id"),
        {"process_instance_id": process_instance_id},
    ).scalar()
    if isinstance(tenant_id, str) and tenant_id:
        return tenant_id
    return None


@celery.signals.task_prerun.connect  # type: ignore
def set_tenant_context_for_task(
    task_id: str | None = None, task: Any | None = None, args: Any = None, kwargs: Any = None, **_signal_kwargs: Any
) -> None:
    if task is None:
        return

    tenant_id: str | None = None
    request = getattr(task, "request", None)
    headers = getattr(request, "headers", None)
    if isinstance(headers, dict):
        header_tenant = headers.get(TENANT_HEADER_NAME)
        if isinstance(header_tenant, str) and header_tenant:
            tenant_id = header_tenant

    if tenant_id is None:
        process_instance_id = _extract_process_instance_id(task.name, args, kwargs)
        if process_instance_id is not None:
            tenant_id = _tenant_id_for_process_instance(process_instance_id)

    if tenant_id and task_id:
        _TASK_TENANT_TOKENS[task_id] = set_context_tenant_id(tenant_id)


@celery.signals.task_postrun.connect  # type: ignore
def clear_tenant_context_for_task(task_id: str | None = None, **_signal_kwargs: Any) -> None:
    if task_id is None:
        return
    token = _TASK_TENANT_TOKENS.pop(task_id, None)
    if token is not None:
        reset_context_tenant_id(token)


@celery.signals.after_setup_logger.connect  # type: ignore
def setup_loggers(logger: Any, *args: Any, **kwargs: Any) -> None:
    log_formatter = get_log_formatter(the_flask_app)
    logger.handlers = []
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(log_formatter)
    logger.addHandler(stdout_handler)
    setup_logger_for_app(the_flask_app, logger, force_run_with_celery=True)
