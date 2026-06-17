"""Observability Middleware

Logs request/response for debugging and performance monitoring.

Benefits:
- Request logging (what tool was called, with what params)
- Response logging (success/failure, timing)
- Error logging (stack traces)
- Performance metrics (how long did it take)
"""

import time
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from src.utils.logging import logger


class ObservabilityMiddleware(Middleware):
    """Middleware for logging requests and responses"""

    async def on_message(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        """Log request, call next middleware/tool, log response"""

        # Start timing
        start_time = time.time()

        try:
            # Log incoming request (without method - not available in FastMCP context)
            logger.info("MCP Request received")

            # Call next middleware or tool
            result = await call_next(context)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log successful response
            logger.info(
                f"MCP Response completed in {round(duration_ms, 2)}ms",
                extra={"params": {"duration_ms": round(duration_ms, 2), "status": "success"}}
            )

            return result

        except Exception as error:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            logger.error(
                f"MCP Error: {str(error)} (after {round(duration_ms, 2)}ms)",
                extra={"params": {"duration_ms": round(duration_ms, 2), "status": "error", "error": str(error)}},
                exc_info=True
            )

            # Re-raise the error
            raise
