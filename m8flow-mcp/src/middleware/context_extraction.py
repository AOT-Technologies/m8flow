"""Middleware for extracting context required for tools execution."""

from __future__ import annotations

import os
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from src.auth.token_service import token_service
from src.config import settings
from src.utils.context import set_auth_token
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ContextExtractionMiddleware(Middleware):
    """Middleware for extracting authentication token and other context.

    Supports multiple token sources (priority order):
    1. Explicit M8FLOW_BEARER_TOKEN from environment
    2. Auto-fetched via ROPC (username/password)
    """

    async def on_call_tool(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        """Extract context and set it for tools to use.

        Args:
            context: Middleware context
            call_next: Next middleware or handler

        Returns:
            Result from next handler
        """
        auth_token: str | None = None

        # NOTE: This middleware is no longer actively used because FastMCP
        # doesn't reliably invoke on_call_tool for all tool calls.
        # Authentication is now set globally at server startup in main.py
        # This code is kept for reference but won't execute.

        logger.debug("Context extraction middleware called (not used)")

        # Priority 1: Explicit bearer token from environment
        auth_token = (
            os.getenv("M8FLOW_BEARER_TOKEN") or os.getenv("FORMSFLOW_BEARER_TOKEN") or settings.m8flow_bearer_token
        )

        if auth_token:
            logger.debug(f"Token available (length: {len(auth_token)} chars)")
        else:
            # Priority 2: Auto-fetch via ROPC (if configured)
            try:
                auth_token = await token_service.get_token()
                logger.debug("Using auto-fetched ROPC token")
            except RuntimeError as e:
                logger.warning(f"Failed to fetch ROPC token: {e}")

        if auth_token:
            # Ensure Bearer prefix
            if not auth_token.startswith("Bearer "):
                auth_token = f"Bearer {auth_token}"
            set_auth_token(auth_token)
            logger.debug(f"Auth token set in context (length: {len(auth_token)})")
        else:
            logger.error("No authentication token available")

        result = await call_next(context)
        return result
