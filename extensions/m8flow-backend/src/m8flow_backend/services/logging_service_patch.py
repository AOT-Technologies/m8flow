# extensions/m8flow-backend/src/m8flow_backend/services/logging_service_patch.py
from __future__ import annotations

import logging
from flask import g, has_request_context

from m8flow_backend.tenancy import DEFAULT_TENANT_ID, get_context_tenant_id, is_request_active

_PATCHED = False
_ORIGINAL_SETUP = None


def _resolve_tenant_id_for_logging(record: logging.LogRecord) -> str:
    """Resolve tenant id for logging purposes."""
    # 1) Normal Flask request logs
    if has_request_context():
        tid = getattr(g, "m8flow_tenant_id", None)
        if tid:
            return tid
        return get_context_tenant_id() or DEFAULT_TENANT_ID

    # 2) Uvicorn access logs: these are emitted by uvicorn, outside Flask context.
    if record.name == "uvicorn.access":
        return get_context_tenant_id() or DEFAULT_TENANT_ID

    # 3) Any other “request-ish” background where we may still want default
    if is_request_active():
        return get_context_tenant_id() or DEFAULT_TENANT_ID

    # 4) Startup / background / truly non-request
    return get_context_tenant_id() or "system"


class TenantContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "m8flow_tenant_id", None):
            record.m8flow_tenant_id = _resolve_tenant_id_for_logging(record)
        return True


class TenantAwareFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if not getattr(record, "m8flow_tenant_id", None):
            record.m8flow_tenant_id = _resolve_tenant_id_for_logging(record)
        return super().format(record)


def _get_log_formatter(app) -> logging.Formatter:
    return TenantAwareFormatter("%(m8flow_tenant_id)s - %(asctime)s %(levelname)s [%(name)s] %(message)s")


def _apply_formatter_to_all_handlers(log_formatter: logging.Formatter) -> None:
    seen = set()
    root_logger = logging.getLogger()

    for handler in root_logger.handlers:
        if id(handler) in seen:
            continue
        handler.setFormatter(log_formatter)
        seen.add(id(handler))

    for logger in logging.root.manager.loggerDict.values():
        if not isinstance(logger, logging.Logger):
            continue
        for handler in logger.handlers:
            if id(handler) in seen:
                continue
            handler.setFormatter(log_formatter)
            seen.add(id(handler))


def apply() -> None:
    """Patch logging service to include tenant context in logs."""
    global _PATCHED, _ORIGINAL_SETUP
    if _PATCHED:
        return

    # Keep this import inside apply() so uvicorn log-config imports of
    # TenantContextFilter do not pull spiffworkflow_backend too early.
    from spiffworkflow_backend.services import logging_service

    if _ORIGINAL_SETUP is None:
        _ORIGINAL_SETUP = logging_service.setup_logger_for_app

        def patched_setup_logger_for_app(app, primary_logger, force_run_with_celery: bool = False) -> None:
            _ORIGINAL_SETUP(app, primary_logger, force_run_with_celery=force_run_with_celery)
            _apply_formatter_to_all_handlers(logging_service.get_log_formatter(app))

        logging_service.setup_logger_for_app = patched_setup_logger_for_app  # type: ignore[assignment]

    logging_service.get_log_formatter = _get_log_formatter  # type: ignore[assignment]
    _PATCHED = True
