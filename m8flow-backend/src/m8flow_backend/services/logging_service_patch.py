# m8flow-backend/src/m8flow_backend/services/logging_service_patch.py
from __future__ import annotations

import logging

from flask import g, has_request_context

from m8flow_backend.tenancy import (
    get_context_tenant_id,
    is_concrete_tenant_id,
    is_legacy_placeholder_tenant_id,
    is_request_active,
)

_PATCHED = False
_ORIGINAL_SETUP = None


def _normalize_tenant_id_for_logging(tenant_id: object) -> str | None:
    if not isinstance(tenant_id, str):
        return None

    normalized_tenant_id = tenant_id.strip()
    if not normalized_tenant_id or is_legacy_placeholder_tenant_id(normalized_tenant_id):
        return None
    if normalized_tenant_id == "public":
        return "public"
    if not is_concrete_tenant_id(normalized_tenant_id):
        return None
    return normalized_tenant_id


def _resolve_tenant_id_for_logging(record: logging.LogRecord) -> str:
    """Resolve tenant id for logging purposes."""
    if has_request_context():
        if getattr(g, "_m8flow_public_request", False):
            return "public"
        if getattr(g, "_m8flow_global_request", False):
            return "global"

        request_tenant_id = _normalize_tenant_id_for_logging(getattr(g, "m8flow_tenant_id", None))
        if request_tenant_id:
            return request_tenant_id

        context_tenant_id = _normalize_tenant_id_for_logging(get_context_tenant_id())
        if context_tenant_id:
            return context_tenant_id

        if getattr(g, "_m8flow_tenant_context_exempt_request", False):
            return "global"
        return "global"

    context_tenant_id = _normalize_tenant_id_for_logging(get_context_tenant_id())
    if context_tenant_id:
        return context_tenant_id

    if record.name == "uvicorn.access":
        return "global"

    if is_request_active():
        return "global"

    return "system"


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
