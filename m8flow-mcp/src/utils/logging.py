"""Logging utilities for m8flow MCP server."""

from __future__ import annotations

import logging
import sys
from typing import Any

from src.config import settings

try:
    from m8flow_telemetry.bootstrap import is_telemetry_enabled, setup

    from src.utils.context import get_tenant_id
except ImportError:  # pragma: no cover
    setup = None
    is_telemetry_enabled = None

    def get_tenant_id() -> None:  # type: ignore[assignment,misc]
        return None


def setup_logging() -> None:
    """Configure logging for the application."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
        force=True,
    )

    logging.getLogger().setLevel(log_level)
    for logger_name in list(logging.Logger.manager.loggerDict.keys()):
        existing_logger = logging.getLogger(logger_name)
        existing_logger.setLevel(log_level)

    if setup is not None:
        setup("m8flow-mcp", tenant_resolver=get_tenant_id)

        # m8flow-mcp always calls out to m8flow-backend over the shared httpx
        # client (both stdio and remote transports) — without this, the trace
        # started per tool call in ObservabilityMiddleware never propagates
        # onward via traceparent, breaking cross-service correlation entirely.
        if is_telemetry_enabled is not None and is_telemetry_enabled():
            try:
                from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

                HTTPXClientInstrumentor().instrument()
            except ImportError:
                pass


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance."""
    if name is None:
        name = "m8flow-mcp"
    return logging.getLogger(name)


def with_params(params: dict[str, Any]) -> dict[str, Any]:
    """Format parameters for structured logging."""
    return {"extra": params} if params else {}


logger = get_logger("m8flow-mcp")
