"""Middleware for extracting tenant context from JWT tokens."""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from src.auth.jwt_utils import TENANT_ID_CLAIM, decode_jwt_claims
from src.config import settings
from src.utils.context import get_auth_token, get_tenant_id, set_tenant_id
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TenantContextMiddleware(Middleware):
    """Middleware for extracting the m8flow tenant id from JWT claims."""

    async def on_message(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        """Extract tenant ID from JWT and set in context.

        Args:
            context: Middleware context
            call_next: Next middleware or handler

        Returns:
            Result from next handler
        """
        auth_token = get_auth_token()

        if auth_token:
            claims = decode_jwt_claims(auth_token)
            tenant_id = claims.get(TENANT_ID_CLAIM)
            if tenant_id:
                set_tenant_id(str(tenant_id))
                logger.debug(f"Tenant context extracted from JWT: {tenant_id}")
            else:
                logger.debug(f"No {TENANT_ID_CLAIM} found in JWT claims")

        # Fallback to DEFAULT_TENANT_ID if not set from JWT
        if not get_tenant_id() and settings.default_tenant_id:
            set_tenant_id(settings.default_tenant_id)
            logger.debug(f"Using default tenant from config: {settings.default_tenant_id}")

        return await call_next(context)
