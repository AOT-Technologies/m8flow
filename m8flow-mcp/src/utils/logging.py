"""Logging utilities for m8flow MCP server."""

from __future__ import annotations

import logging
import sys
from typing import Any

from src.config import settings


def setup_logging() -> None:
    """Configure logging for the application."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure root logger
    # IMPORTANT: Use stderr for stdio mode to not interfere with MCP protocol
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    # Set level for all existing loggers (in case they were created before setup)
    logging.getLogger().setLevel(log_level)
    for logger_name in list(logging.Logger.manager.loggerDict.keys()):
        existing_logger = logging.getLogger(logger_name)
        existing_logger.setLevel(log_level)


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name. If None, returns root logger.

    Returns:
        Logger instance.
    """
    if name is None:
        name = "m8flow-mcp"
    return logging.getLogger(name)


def with_params(params: dict[str, Any]) -> dict[str, Any]:
    """Format parameters for structured logging.

    Args:
        params: Dictionary of parameters to log.

    Returns:
        Formatted parameters dictionary.
    """
    return {"extra": params} if params else {}


# Create default logger instance for direct import
logger = get_logger("m8flow-mcp")
