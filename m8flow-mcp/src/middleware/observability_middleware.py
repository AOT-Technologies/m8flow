"""Observability Middleware — OTel spans + domain metrics for MCP tool calls."""

from __future__ import annotations

import time
from typing import Any
import contextlib

from fastmcp.server.middleware import Middleware, MiddlewareContext

from src.config import settings
from src.utils.context import get_tenant_id
from src.utils.logging import logger, with_params

try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind

    TRACER = trace.get_tracer("m8flow.mcp")
except ImportError:  # pragma: no cover
    trace = None
    SpanKind = None
    TRACER = None

try:
    from m8flow_telemetry.metrics import record_mcp_tool_call
except ImportError:  # pragma: no cover
    record_mcp_tool_call = None


class ObservabilityMiddleware(Middleware):
    """Middleware for logging requests and responses with OpenTelemetry."""

    async def on_message(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        start_time = time.time()
        tool_name = getattr(context, "name", None) or getattr(context, "method", None) or "unknown"
        transport = "streamable-http" if settings.is_remote else "stdio"
        failed = False

        span_cm = (
            TRACER.start_as_current_span(
                "mcp.tool",
                kind=SpanKind.SERVER,
                attributes={"mcp.tool.name": str(tool_name)},
            )
            if TRACER is not None and SpanKind is not None
            else contextlib.nullcontext()
        )

        with span_cm as span:
            try:
                logger.info("MCP Request received", extra=with_params({"tool_name": tool_name, "transport": transport}))
                result = await call_next(context)
                return result
            except Exception as error:
                failed = True
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"MCP Error: {str(error)} (after {round(duration_ms, 2)}ms)",
                    extra=with_params(
                        {
                            "duration_ms": round(duration_ms, 2),
                            "status": "error",
                            "error": str(error),
                            "tool_name": tool_name,
                        }
                    ),
                    exc_info=True,
                )
                raise
            finally:
                # Tenant resolution (ContextExtractionMiddleware / TenantContextMiddleware)
                # happens inside call_next, nested below this middleware (registered
                # outermost so it wraps everything) — read it now, not before call_next,
                # or every span/metric here would carry a stale or empty tenant_id.
                tenant_id = get_tenant_id()
                if span is not None and tenant_id:
                    span.set_attribute("m8flow_tenant_id", tenant_id)

                duration_ms = (time.time() - start_time) * 1000
                if record_mcp_tool_call is not None:
                    record_mcp_tool_call(
                        tenant_id,
                        tool_name=str(tool_name),
                        transport=transport,
                        duration_ms=duration_ms,
                        failed=failed,
                    )
                if not failed:
                    logger.info(
                        f"MCP Response completed in {round(duration_ms, 2)}ms",
                        extra=with_params(
                            {
                                "duration_ms": round(duration_ms, 2),
                                "status": "success",
                                "tool_name": tool_name,
                            }
                        ),
                    )
