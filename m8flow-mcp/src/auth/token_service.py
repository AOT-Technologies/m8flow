"""Automatic Keycloak token management via Resource Owner Password Credentials.

Uses the ROPC grant to fetch access tokens with username/password.
Tokens are cached until shortly before expiry and automatically refreshed.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TokenService:
    """Fetches and caches a Keycloak access token (ROPC grant)."""

    def __init__(
        self,
        keycloak_url: str | None = None,
        realm: str | None = None,
        http_relative_path: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        username: str | None = None,
        password: str | None = None,
        refresh_margin: int = 30,
    ) -> None:
        """Initialize token service.

        Args:
            keycloak_url: Keycloak base URL (default: from settings)
            realm: Realm name (default: from settings)
            http_relative_path: HTTP path prefix (default: /auth)
            client_id: Client ID (default: from settings)
            client_secret: Optional client secret (for confidential clients)
            username: Username for ROPC (default: from settings)
            password: Password for ROPC (default: from settings)
            refresh_margin: Refresh token N seconds before expiry (default: 30)
        """
        kc_url = (keycloak_url or settings.keycloak_url).rstrip("/")
        _realm = realm or settings.keycloak_realm
        _path = http_relative_path or ""

        self.token_url = f"{kc_url}{_path}/realms/{_realm}/protocol/openid-connect/token"
        self.client_id = client_id or settings.client_id
        self.client_secret = client_secret or settings.client_secret
        self.username = username or settings.keycloak_username or ""
        self.password = password or settings.keycloak_password or ""
        self._refresh_margin = refresh_margin

        self._access_token: str | None = None
        self._expires_at: float = 0

    @property
    def _is_expired(self) -> bool:
        """Check if cached token is expired (with margin)."""
        return time.time() >= (self._expires_at - self._refresh_margin)

    async def get_token(self) -> str:
        """Return a valid access token, refreshing if necessary.

        Returns:
            Valid JWT access token

        Raises:
            RuntimeError: If credentials not configured or token fetch fails
        """
        # Use cached token if still valid
        if self._access_token and not self._is_expired:
            return self._access_token

        # Validate credentials
        if not self.username or not self.password:
            raise RuntimeError(
                "KEYCLOAK_USERNAME and KEYCLOAK_PASSWORD must be set in .env "
                "for automatic token acquisition via ROPC"
            )

        # Fetch new token
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                form_data = {
                    "grant_type": "password",
                    "client_id": self.client_id,
                    "username": self.username,
                    "password": self.password,
                }

                # Add client_secret for confidential clients
                if self.client_secret:
                    form_data["client_secret"] = self.client_secret

                resp = await client.post(
                    self.token_url,
                    data=form_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                data = resp.json()

        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            logger.error(f"Keycloak token request failed ({exc.response.status_code}): {body}")
            raise RuntimeError(f"Keycloak token request failed ({exc.response.status_code}): {body}") from exc

        except httpx.HTTPError as exc:
            logger.error(f"Failed to reach Keycloak token endpoint: {exc}")
            raise RuntimeError(f"Keycloak token request failed: {exc}") from exc

        # Cache token
        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 300)
        self._expires_at = time.time() + expires_in

        # Log token info (decode payload for debugging)
        self._log_token_info(self._access_token, expires_in)

        return self._access_token

    def _log_token_info(self, token: str, expires_in: int) -> None:
        """Log token information for debugging.

        Args:
            token: JWT token
            expires_in: Token expiry in seconds
        """
        try:
            # Decode JWT payload (no verification needed for logging)
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)  # Add padding
            claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(payload_b64))

            logger.info(
                f"ROPC token acquired for '{self.username}' (expires in {expires_in}s) "
                f"iss={claims.get('iss')} "
                f"aud={claims.get('aud')} "
                f"azp={claims.get('azp')} "
                f"tenant={claims.get('m8f_tenant_id')} "
                f"roles={claims.get('realm_access', {}).get('roles', [])[:3]}"
            )
        except Exception as e:
            logger.info(f"ROPC token acquired for '{self.username}' (expires in {expires_in}s)")
            logger.debug(f"Failed to decode token for logging: {e}")


# Module-level singleton — initialized from env vars on first import
token_service = TokenService()
