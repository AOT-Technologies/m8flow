"""Simplified token service - no JWT validation, just ROPC with caching."""

import os
import time
import httpx
from src.utils.logging import get_logger

logger = get_logger(__name__)

class TokenService:
    """Simple ROPC token service with caching."""

    def __init__(self) -> None:
        self._cached_token: str | None = None
        self._cached_expires_at: float = 0.0

    async def get_token(self) -> str:
        """Get token: env var > cached > fresh ROPC."""
        # Priority 1: Direct bearer token
        token = os.getenv("M8FLOW_BEARER_TOKEN", "").strip()
        if token:
            return token

        # Priority 2: Cached token
        if self._cached_token and time.time() < (self._cached_expires_at - 30):
            return self._cached_token

        # Priority 3: Fetch via ROPC
        url = f"{os.getenv('KEYCLOAK_URL', 'http://localhost:6842').rstrip('/')}/realms/{os.getenv('KEYCLOAK_REALM', 'm8flow')}/protocol/openid-connect/token"

        username = os.getenv("KEYCLOAK_USERNAME", "").strip()
        password = os.getenv("KEYCLOAK_PASSWORD", "").strip()

        if not username or not password:
            raise RuntimeError("Set M8FLOW_BEARER_TOKEN or KEYCLOAK_USERNAME/PASSWORD")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data={
                "grant_type": "password",
                "client_id": os.getenv("CLIENT_ID", "m8flow-mcp"),
                "username": username,
                "password": password,
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})

        if resp.status_code >= 400:
            raise RuntimeError(f"Keycloak failed ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        access_token: str = data.get("access_token", "").strip()
        if not access_token:
            raise RuntimeError(f"No access_token in response: {data}")

        self._cached_token = access_token
        self._cached_expires_at = time.time() + int(data.get("expires_in", 300))

        logger.info(f"Token acquired for '{username}'")
        return access_token
