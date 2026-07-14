"""Automatic Keycloak token management via Resource Owner Password Credentials.

Uses the ROPC (password) grant so the resulting JWT carries the real user's
roles and ``m8flow_tenant_id``. The token is cached until shortly before expiry
and refreshed transparently.

Both an async (``get_token``) and a sync (``get_token_sync``) accessor are
provided. The sync variant lets the existing synchronous ``get_auth_token()``
call sites resolve a token without every tool becoming ``async``.

``settings.keycloak_token_url`` must resolve to the token endpoint reachable
from this process so the ``iss`` claim matches what the backend expects. Enable
"Direct Access Grants" on the Keycloak client for ROPC to work.
"""

from __future__ import annotations

import threading
import time

import httpx

from src.auth.jwt_utils import TENANT_ID_CLAIM, decode_jwt_claims
from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TokenService:
    """Fetches and caches a Keycloak access token (ROPC grant)."""

    def __init__(self, refresh_margin: int | None = None) -> None:
        self._refresh_margin = refresh_margin if refresh_margin is not None else settings.token_refresh_margin
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def _is_expired(self) -> bool:
        return time.time() >= (self._expires_at - self._refresh_margin)

    def _build_form(self) -> dict[str, str]:
        if not settings.has_ropc_credentials:
            raise RuntimeError(
                "KEYCLOAK_USERNAME and KEYCLOAK_PASSWORD must be set for automatic "
                "(ROPC) token acquisition, or provide M8FLOW_BEARER_TOKEN instead."
            )
        form = {
            "grant_type": "password",
            "client_id": settings.client_id,
            "username": settings.keycloak_username or "",
            "password": settings.keycloak_password or "",
            "scope": " ".join(settings.required_scopes_list) or "openid",
        }
        if settings.client_secret:
            form["client_secret"] = settings.client_secret
        return form

    def _store(self, data: dict) -> str:
        access_token = data["access_token"]
        self._access_token = access_token
        self._expires_at = time.time() + int(data.get("expires_in", 300))

        claims = decode_jwt_claims(access_token)
        logger.info(
            "ROPC token acquired for '%s' (expires in %ss) iss=%s aud=%s tenant=%s",
            settings.keycloak_username,
            data.get("expires_in", 300),
            claims.get("iss"),
            claims.get("aud"),
            claims.get(TENANT_ID_CLAIM),
        )
        return access_token

    async def get_token(self) -> str:
        """Return a valid access token, refreshing via async HTTP if necessary."""
        if self._access_token and not self._is_expired:
            return self._access_token

        form = self._build_form()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    settings.keycloak_token_url,
                    data=form,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            logger.error("Keycloak token request failed (%s): %s", exc.response.status_code, body)
            raise RuntimeError(f"Keycloak token request failed ({exc.response.status_code}): {body}") from exc
        except httpx.HTTPError as exc:
            logger.error("Failed to reach Keycloak token endpoint: %s", exc)
            raise RuntimeError(f"Keycloak token request failed: {exc}") from exc

        return self._store(data)

    def get_token_sync(self) -> str:
        """Return a valid access token, refreshing via sync HTTP if necessary.

        Safe to call from synchronous code (e.g. ``get_auth_token``). A lock
        prevents concurrent refreshes from stampeding the token endpoint.
        """
        if self._access_token and not self._is_expired:
            return self._access_token

        with self._lock:
            # Re-check inside the lock in case another thread just refreshed.
            if self._access_token and not self._is_expired:
                return self._access_token

            form = self._build_form()
            try:
                with httpx.Client(timeout=15) as client:
                    resp = client.post(
                        settings.keycloak_token_url,
                        data=form,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:300]
                logger.error("Keycloak token request failed (%s): %s", exc.response.status_code, body)
                raise RuntimeError(f"Keycloak token request failed ({exc.response.status_code}): {body}") from exc
            except httpx.HTTPError as exc:
                logger.error("Failed to reach Keycloak token endpoint: %s", exc)
                raise RuntimeError(f"Keycloak token request failed: {exc}") from exc

            return self._store(data)


# Module-level singleton — initialised from settings on first import.
token_service = TokenService()
