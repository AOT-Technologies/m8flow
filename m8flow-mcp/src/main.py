"""Main entry point for m8flow MCP server."""

from __future__ import annotations

import sys

from fastmcp import FastMCP

from src.config import settings
from src.middleware import (
    ContextExtractionMiddleware,
    ObservabilityMiddleware,
    TenantContextMiddleware,
)
from src.mcp_tools import register_tools
from src.utils.logging import get_logger, setup_logging

# Setup logging
setup_logging()
logger = get_logger(__name__)

# Create FastMCP server
mcp = FastMCP("m8flow")

# Add middleware (order matters: observability wraps everything)
mcp.add_middleware(ObservabilityMiddleware())
mcp.add_middleware(ContextExtractionMiddleware())
mcp.add_middleware(TenantContextMiddleware())

# Set authentication token at startup
# NOTE: Middleware-based auth doesn't work reliably with FastMCP 3.4.2
# as on_call_tool isn't consistently invoked. Setting globally instead.
import os
from src.utils.context import set_auth_token, set_tenant_id
import json
import base64

# Get token from environment or settings
auth_token = (
    os.getenv("M8FLOW_BEARER_TOKEN")
    or os.getenv("FORMSFLOW_BEARER_TOKEN")
    or settings.m8flow_bearer_token
)

if auth_token:
    # Ensure Bearer prefix
    if not auth_token.startswith("Bearer "):
        auth_token = f"Bearer {auth_token}"
    set_auth_token(auth_token)

    # Extract tenant ID from JWT token
    try:
        token_part = auth_token.replace("Bearer ", "")
        parts = token_part.split('.')
        if len(parts) == 3:
            # Decode JWT payload
            payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            tenant_id = claims.get('m8flow_tenant_id')
            if tenant_id:
                set_tenant_id(tenant_id)
                logger.info(f"Authentication configured: user={claims.get('preferred_username')}, tenant={tenant_id[:20]}...")
            else:
                logger.warning("No m8flow_tenant_id found in JWT claims")
    except Exception as e:
        logger.warning(f"Could not extract tenant from token: {e}")

    logger.info(f"Auth token configured (length: {len(auth_token)} chars)")
else:
    logger.error("No authentication token available - set M8FLOW_BEARER_TOKEN in environment or .env file")

# Register all tools
register_tools(mcp)

logger.info(f"m8flow MCP server initialized in {settings.server_type} mode")


def main() -> int:
    """Run the MCP server.

    Returns:
        Exit code
    """
    try:
        if settings.is_remote:
            # HTTP mode for Cursor
            logger.info(f"Starting m8flow MCP server in HTTP mode on {settings.host}:{settings.port}")
            mcp.run(
                transport="streamable-http",
                host=settings.host,
                port=settings.port,
            )
        else:
            # stdio mode for Claude Desktop
            logger.info("Starting m8flow MCP server in stdio mode")
            mcp.run(transport="stdio")

        return 0

    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0

    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
