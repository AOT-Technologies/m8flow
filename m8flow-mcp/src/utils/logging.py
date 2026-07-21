"""Logging utilities for m8flow MCP server."""

from __future__ import annotations

import logging
import sys
from typing import Any

from src.config import settings

try:
    from m8flow_telemetry.bootstrap import setup
    from src.utils.context import get_tenant_id
except ImportError:  # pragma: no cover
    setup = None
    get_tenant_id = lambda: None  # type: ignore[assignment,misc]


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


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance."""
    if name is None:
        name = "m8flow-mcp"
    return logging.getLogger(name)


def with_params(params: dict[str, Any]) -> dict[str, Any]:
    """Format parameters for structured logging."""
    return {"extra": params} if params else {}


logger = get_logger("m8flow-mcp")
