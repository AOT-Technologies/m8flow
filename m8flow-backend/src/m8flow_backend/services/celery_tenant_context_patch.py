from __future__ import annotations

from typing import Any

import celery

from m8flow_backend.tenancy import get_tenant_id

TENANT_HEADER_NAME = "x-m8flow-tenant-id"

_PATCHED = False
_ORIGINAL_SEND_TASK = None


def _current_tenant_id() -> str | None:
    try:
        tenant_id = get_tenant_id(warn_on_default=False)
    except Exception:
        return None
    if isinstance(tenant_id, str) and tenant_id:
        return tenant_id
    return None


def apply() -> None:
    global _PATCHED, _ORIGINAL_SEND_TASK
    if _PATCHED:
        return

    _ORIGINAL_SEND_TASK = celery.Celery.send_task

    def _patched_send_task(self: Any, name: str, args: Any = None, kwargs: Any = None, **options: Any) -> Any:
        headers = dict(options.get("headers") or {})
        if TENANT_HEADER_NAME not in headers:
            tenant_id = _current_tenant_id()
            if tenant_id:
                headers[TENANT_HEADER_NAME] = tenant_id
                options["headers"] = headers

        return _ORIGINAL_SEND_TASK(self, name, args=args, kwargs=kwargs, **options)  # type: ignore[misc]

    celery.Celery.send_task = _patched_send_task
    _PATCHED = True

