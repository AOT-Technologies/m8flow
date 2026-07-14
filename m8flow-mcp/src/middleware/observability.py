"""Observability middleware for logging and monitoring MCP tool calls."""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from src.utils.context import get_tenant_id
from src.utils.logging import get_logger, with_params

logger = get_logger(__name__)


class ObservabilityMiddleware(Middleware):
    """Middleware for logging and monitoring MCP tool calls."""

    def _create_log_context(self, context: MiddlewareContext[Any]) -> dict[str, Any]:
        """Create log data dictionary from context.

        Args:
            context: Middleware context

        Returns:
            Log context dictionary
        """
        return {
            "method": context.method,
            "resource_name": getattr(context.message, "name", "N/A"),
            "resource_params": getattr(context.message, "arguments", "N/A"),
            "tenant_id": get_tenant_id(),
        }

    async def on_message(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        """Hook for all messages - handles logging and error tracking.

        Args:
            context: Middleware context
            call_next: Next middleware or handler

        Returns:
            Result from next handler

        Raises:
            Exception: Re-raises any exceptions after logging
        """
        try:
            result = await call_next(context)

            # Prepare log data
            log_data = self._create_log_context(context)

            # Log successful operations
            logger.info("MCP operation completed successfully", extra=with_params(log_data))

            return result

        except Exception as e:
            # Log error
            logger.error(
                "MCP operation failed",
                extra=with_params({"error": str(e)} | self._create_log_context(context)),
                exc_info=True,
            )

            # Re-raise to allow error handling middleware to process
            raise
