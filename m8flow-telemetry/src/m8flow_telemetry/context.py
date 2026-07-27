from __future__ import annotations

from contextvars import ContextVar
from typing import Callable

TenantResolver = Callable[[], str | None]

_tenant_id: ContextVar[str | None] = ContextVar("m8flow_telemetry_tenant_id", default=None)


def set_tenant_id(tenant_id: str | None) -> None:
    _tenant_id.set(tenant_id)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def default_tenant_resolver() -> str | None:
    return get_tenant_id()
