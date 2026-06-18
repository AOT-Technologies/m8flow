"""Middleware for extracting tenant context from JWT tokens."""

from __future__ import annotations

import base64
import json
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from src.config import settings
from src.utils.context import get_auth_token, set_tenant_id
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TenantContextMiddleware(Middleware):
    """Middleware for extracting m8f_tenant_id from JWT claims."""

    def _decode_jwt_claims(self, token: str) -> dict[str, Any] | None:
        """Decode JWT token to extract claims (without verification).

        Args:
            token: JWT token string

        Returns:
            Claims dictionary or None if decoding fails

        Note:
            This does NOT verify the signature - that should be done by Keycloak.
            We just extract claims for tenant context.
        """
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith("Bearer "):
                token = token[7:]

            # JWT format: header.payload.signature
            parts = token.split(".")
            if len(parts) != 3:
                logger.warning("Invalid JWT format")
                return None

            # Decode payload (add padding if needed)
            payload = parts[1]
            padding = len(payload) % 4
            if padding:
                payload += "=" * (4 - padding)

            decoded = base64.urlsafe_b64decode(payload)
            claims: dict[str, Any] = json.loads(decoded)
            return claims

        except Exception as e:
            logger.warning(f"Failed to decode JWT claims: {e}")
            return None

    async def on_message(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        """Extract tenant ID from JWT and set in context.

        Args:
            context: Middleware context
            call_next: Next middleware or handler

        Returns:
            Result from next handler
        """
        # Get auth token from context (set by ContextExtractionMiddleware)
        auth_token = get_auth_token()

        if auth_token:
            claims = self._decode_jwt_claims(auth_token)
            if claims:
                # Extract m8f_tenant_id from JWT claims
                tenant_id = claims.get("m8f_tenant_id")
                if tenant_id:
                    set_tenant_id(str(tenant_id))
                    logger.debug(f"Tenant context extracted from JWT: {tenant_id}")
                else:
                    logger.debug("No m8f_tenant_id found in JWT claims")

        # Fallback to DEFAULT_TENANT_ID if not set from JWT
        from src.utils.context import get_tenant_id

        if not get_tenant_id() and settings.default_tenant_id:
            set_tenant_id(settings.default_tenant_id)
            logger.debug(f"Using default tenant from config: {settings.default_tenant_id}")

        result = await call_next(context)
        return result
