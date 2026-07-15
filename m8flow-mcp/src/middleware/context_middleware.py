"""Context Extraction Middleware

Extracts auth token and tenant context once per request and stores it in
FastMCP context state for use by all tools.

Benefits:
- DRY: Extract once, use everywhere (no repeated get_bearer_token() calls)
- Centralized: Auth logic in one place
- Clean: Tools don't need to worry about auth extraction
"""

from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

# from simple_auth import get_bearer_token  # Not needed - deprecated middleware
from src.config import settings
from src.utils.context import AUTH_TOKEN_KEY


class ContextExtractionMiddleware(Middleware):
    """Middleware for extracting auth token and tenant context.

    Runs before every tool call to:
    1. Extract bearer token (from env or ROPC)
    2. Set tenant context (from DEFAULT_TENANT_ID)
    3. Store in FastMCP context state
    """

    async def on_message(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        """Extract token and tenant, store in context, then continue"""

        fastmcp_context = context.fastmcp_context
        if fastmcp_context is None:
            # No context available (shouldn't happen, but handle gracefully)
            return await call_next(context)

        # Get bearer token from settings
        if settings.m8flow_bearer_token:
            # Store in context state for tools to retrieve
            await fastmcp_context.set_state(AUTH_TOKEN_KEY, settings.m8flow_bearer_token)

        # Tenant resolution is handled by TenantContextMiddleware, which is
        # multi-tenant-aware (a blanket DEFAULT_TENANT_ID here would mask the
        # tenant a multi-tenant user selected during authentication).

        # Continue to next middleware or tool
        return await call_next(context)
