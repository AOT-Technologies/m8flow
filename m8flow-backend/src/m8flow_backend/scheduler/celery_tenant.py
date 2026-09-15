"""Celery publish/worker tenant propagation via x-m8flow-tenant-id.

Host-native: the rewrite does not revive overlay ``celery_tenant_context_patch``
or ``celery_worker_runtime``. Beat ``poll_due`` has no HTTP tenant; that path
iterates active tenants in ``scheduler.poll_due_jobs`` instead of publishing
a header.
"""
from __future__ import annotations

from contextvars import Token
from typing import Any

from celery import Celery

from m8flow_backend.auth.canonicalize import current_tenant_id_or_none
from m8flow_backend.auth.tenant_context import (
    TENANT_SELECTION_HEADER_NAME,
    is_concrete_tenant_id,
    reset_context_tenant_id,
    set_context_tenant_id,
)

_TASK_TENANT_TOKENS: dict[str, Token] = {}
_SIGNALS_INSTALLED = False


def tenant_id_from_celery_headers(headers: object) -> str | None:
    if not isinstance(headers, dict):
        return None
    raw = headers.get(TENANT_SELECTION_HEADER_NAME)
    if raw is None:
        for key, value in headers.items():
            if isinstance(key, str) and key.lower() == TENANT_SELECTION_HEADER_NAME:
                raw = value
                break
    if not isinstance(raw, str):
        return None
    tenant_id = raw.strip()
    if not tenant_id or not is_concrete_tenant_id(tenant_id):
        return None
    return tenant_id


class TenantAwareCelery(Celery):
    """Inject the active ContextVar tenant into task headers on publish."""

    def send_task(self, name, args=None, kwargs=None, **options):
        headers = dict(options.get("headers") or {})
        if TENANT_SELECTION_HEADER_NAME not in headers:
            tenant_id = current_tenant_id_or_none()
            if tenant_id:
                headers[TENANT_SELECTION_HEADER_NAME] = tenant_id
                options["headers"] = headers
        return super().send_task(name, args=args, kwargs=kwargs, **options)


def bind_celery_task_tenant(
    sender=None,
    task_id: str | None = None,
    task: Any | None = None,
    **_: Any,
) -> None:
    if not task_id or task is None:
        return
    headers = getattr(getattr(task, "request", None), "headers", None)
    tenant_id = tenant_id_from_celery_headers(headers)
    if not tenant_id:
        return
    _TASK_TENANT_TOKENS[task_id] = set_context_tenant_id(tenant_id)


def clear_celery_task_tenant(sender=None, task_id: str | None = None, **_: Any) -> None:
    if task_id is None:
        return
    token = _TASK_TENANT_TOKENS.pop(task_id, None)
    if token is not None:
        reset_context_tenant_id(token)


def install_celery_tenant_signals() -> None:
    global _SIGNALS_INSTALLED
    if _SIGNALS_INSTALLED:
        return
    from celery.signals import task_postrun, task_prerun

    task_prerun.connect(bind_celery_task_tenant, weak=False)
    task_postrun.connect(clear_celery_task_tenant, weak=False)
    _SIGNALS_INSTALLED = True
