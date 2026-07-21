from __future__ import annotations

import logging
from typing import Callable

from opentelemetry.sdk._logs import LogRecordProcessor, ReadWriteLogRecord

from m8flow_telemetry.context import TenantResolver, default_tenant_resolver

M8FLOW_TENANT_ID_ATTR = "m8flow_tenant_id"


class TenantAttributeLogProcessor(LogRecordProcessor):
    def __init__(self, tenant_resolver: TenantResolver | None = None) -> None:
        self._tenant_resolver = tenant_resolver or default_tenant_resolver

    def on_emit(self, log_record: ReadWriteLogRecord) -> None:
        tenant_id = self._tenant_resolver()
        if tenant_id:
            attrs = log_record.log_record.attributes
            if attrs is None:
                log_record.log_record.attributes = {M8FLOW_TENANT_ID_ATTR: tenant_id}
            else:
                attrs[M8FLOW_TENANT_ID_ATTR] = tenant_id

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class StdlibTenantFilter(logging.Filter):
    """Ensure stdlib LogRecord carries m8flow_tenant_id for console formatters."""

    def __init__(self, tenant_resolver: TenantResolver | None = None) -> None:
        super().__init__()
        self._tenant_resolver = tenant_resolver or default_tenant_resolver

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, M8FLOW_TENANT_ID_ATTR, None):
            tenant_id = self._tenant_resolver()
            if tenant_id:
                setattr(record, M8FLOW_TENANT_ID_ATTR, tenant_id)
        return True


def record_resolver_from_log_record(resolver: Callable[[logging.LogRecord], str]) -> TenantResolver:
    """Wrap a logging.LogRecord-based resolver for services like m8flow-backend."""

    def _wrapped() -> str | None:
        record = logging.LogRecord(
            name="m8flow.telemetry",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="",
            args=(),
            exc_info=None,
        )
        value = resolver(record)
        return value or None

    return _wrapped
