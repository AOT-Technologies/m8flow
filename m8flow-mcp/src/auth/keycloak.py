"""Keycloak JWT validation for the m8flow MCP server.

Validates RS256-signed Bearer tokens against the Keycloak JWKS endpoint,
extracts user roles and tenant information from JWT claims.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from jose import ExpiredSignatureError, JWTError, jwt

from src.auth.jwt_utils import TENANT_ID_CLAIM
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class UserContext:
    """Authenticated user extracted from a validated Keycloak JWT."""

    username: str
    email: str
    roles: list[str]
    groups: list[str]
    tenant_id: str | None  # m8flow_tenant_id from JWT claims
    token: str  # raw bearer token — forwarded to m8flow backend


class AuthError(Exception):
    """Carries an HTTP status code + human-readable detail message."""

    def __init__(self, status_code: int, detail: str) -> None:
        """Initialize auth error.

        Args:
            status_code: HTTP status code
            detail: Error message
        """
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class KeycloakAuth:
    """Validates JWTs issued by a Keycloak realm using its JWKS endpoint.

    Supports RS256 signature verification, automatic JWKS caching with rotation,
    and extraction of m8flow-specific claims (tenant_id, roles).
    """

    def __init__(
        self,
        keycloak_url: str,
        realm: str,
        http_relative_path: str = "/auth",
        client_id: str = "m8flow-mcp",
        jwks_cache_ttl: int = 300,
    ) -> None:
        """Initialize Keycloak authenticator.

        Args:
            keycloak_url: Base Keycloak URL (e.g., http://localhost:8080)
            realm: Realm name (e.g., m8flow)
            http_relative_path: HTTP path prefix (default: /auth)
            client_id: Expected audience (default: m8flow-mcp)
            jwks_cache_ttl: JWKS cache TTL in seconds (default: 300)
        """
        base = f"{keycloak_url.rstrip('/')}{http_relative_path}/realms/{realm}"
        self.jwks_uri = f"{base}/protocol/openid-connect/certs"
        self.issuer = base
        self.audience = client_id
        self._jwks: dict[str, Any] | None = None
        self._jwks_fetched_at: float = 0
        self._cache_ttl = jwks_cache_ttl

    async def _fetch_jwks(self, *, force: bool = False) -> dict[str, Any]:
        """Return cached JWKS or fetch fresh keys from Keycloak.

        Args:
            force: Force refresh even if cached

        Returns:
            JWKS dictionary

        Raises:
            AuthError: If JWKS fetch fails
        """
        now = time.time()
        if not force and self._jwks is not None and (now - self._jwks_fetched_at) < self._cache_ttl:
            return self._jwks

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.jwks_uri)
                resp.raise_for_status()
                self._jwks = resp.json()
                self._jwks_fetched_at = time.time()
                logger.debug(f"Fetched JWKS from {self.jwks_uri}")
                return self._jwks
        except httpx.HTTPError as exc:
            raise AuthError(502, f"Failed to fetch JWKS from Keycloak: {exc}") from exc

    @staticmethod
    def _find_key(jwks: dict[str, Any], kid: str) -> dict[str, Any] | None:
        """Locate the RSA key matching the token's kid header.

        Args:
            jwks: JWKS dictionary
            kid: Key ID

        Returns:
            RSA key or None if not found
        """
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key  # type: ignore[no-any-return]
        return None

    @staticmethod
    def _extract_roles(payload: dict[str, Any]) -> list[str]:
        """Extract roles from JWT payload (m8flow-specific).

        Checks: realm_access.roles, then roles, then role.

        Args:
            payload: JWT payload

        Returns:
            List of role strings
        """
        # Check realm_access.roles first (Keycloak standard)
        realm_roles = payload.get("realm_access", {}).get("roles", [])
        if realm_roles:
            return list(realm_roles)

        # Fallback to top-level roles/role
        roles = payload.get("roles") or payload.get("role") or []
        return [roles] if isinstance(roles, str) else list(roles)

    @staticmethod
    def _extract_tenant_id(payload: dict[str, Any]) -> str | None:
        """Extract m8flow tenant ID from JWT claims.

        Args:
            payload: JWT payload

        Returns:
            Tenant ID or None
        """
        tenant_id = payload.get(TENANT_ID_CLAIM)
        return str(tenant_id) if tenant_id else None

    async def validate_token(self, token: str) -> UserContext:
        """Validate a raw Bearer token and return a UserContext.

        Args:
            token: JWT token string

        Returns:
            UserContext with validated user info

        Raises:
            AuthError: On any validation failure
        """
        # 1. Decode header to find the signing key id
        try:
            header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise AuthError(401, "Malformed JWT token") from exc

        kid = header.get("kid")
        if not kid or not isinstance(kid, str):
            raise AuthError(401, "JWT header missing valid kid")

        # 2. Look up the signing key in JWKS (auto-refresh on miss)
        jwks = await self._fetch_jwks()
        rsa_key = self._find_key(jwks, kid)
        if rsa_key is None:
            # Key rotation? Try fresh JWKS
            logger.info(f"Key {kid} not found in cached JWKS, refreshing...")
            jwks = await self._fetch_jwks(force=True)
            rsa_key = self._find_key(jwks, kid)
            if rsa_key is None:
                raise AuthError(401, "JWT signing key not found in Keycloak JWKS")

        # 3. Decode & verify signature, issuer, and expiration
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False},  # Manual audience check below
            )
        except ExpiredSignatureError as exc:
            raise AuthError(401, "Token has expired") from exc
        except JWTError as exc:
            raise AuthError(401, f"Token validation failed: {exc}") from exc

        # 4. Audience verification — accept token if aud or azp matches
        aud = payload.get("aud", [])
        if isinstance(aud, str):
            aud = [aud]
        azp = payload.get("azp", "")
        if self.audience and self.audience not in aud and self.audience != azp:
            raise AuthError(401, f"Invalid token audience. Expected '{self.audience}'")

        # 5. Build user context
        return UserContext(
            username=payload.get("preferred_username", ""),
            email=payload.get("email", ""),
            roles=self._extract_roles(payload),
            groups=payload.get("groups", []),
            tenant_id=self._extract_tenant_id(payload),
            token=token,
        )
