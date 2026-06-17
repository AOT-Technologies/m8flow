"""Role-Based Access Control (RBAC) for m8flow MCP server.

Extracts user roles from JWT token and validates permissions.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from src.errors import AuthorizationError
from src.utils.logging import logger


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode JWT token payload without verification.

    NOTE: This extracts claims from the token but does NOT verify the signature.
    Token signature verification happens at the m8flow backend API level.

    Args:
        token: JWT bearer token (with or without "Bearer " prefix)

    Returns:
        Decoded JWT payload as dict

    Raises:
        ValueError: If token format is invalid
    """
    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    try:
        # JWT format: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")

        # Decode payload (second part)
        payload = parts[1]

        # Add padding if needed (JWT base64 may omit padding)
        padding = 4 - (len(payload) % 4)
        if padding != 4:
            payload += "=" * padding

        # Decode base64
        decoded_bytes = base64.urlsafe_b64decode(payload)
        decoded_json = json.loads(decoded_bytes)

        return decoded_json

    except Exception as e:
        logger.warning(f"Failed to decode JWT token: {e}")
        raise ValueError(f"Failed to decode JWT token: {e}")


def get_user_roles(token: str) -> list[str]:
    """Extract user roles from JWT token.

    Looks for roles in common JWT claim locations:
    - roles
    - realm_access.roles (Keycloak format)
    - resource_access.<client>.roles (Keycloak client roles)
    - groups

    Args:
        token: JWT bearer token

    Returns:
        List of role names (lowercase for case-insensitive matching)
    """
    try:
        payload = decode_jwt_payload(token)
    except ValueError:
        logger.warning("Could not decode JWT token for RBAC - allowing access")
        return []  # Fail open (no roles, but don't block)

    roles: set[str] = set()

    # Check standard "roles" claim
    if "roles" in payload and isinstance(payload["roles"], list):
        roles.update(r.lower() for r in payload["roles"] if isinstance(r, str))

    # Check Keycloak realm roles
    if "realm_access" in payload and isinstance(payload["realm_access"], dict):
        realm_roles = payload["realm_access"].get("roles", [])
        if isinstance(realm_roles, list):
            roles.update(r.lower() for r in realm_roles if isinstance(r, str))

    # Check Keycloak resource/client roles
    if "resource_access" in payload and isinstance(payload["resource_access"], dict):
        for client, access in payload["resource_access"].items():
            if isinstance(access, dict) and "roles" in access:
                client_roles = access["roles"]
                if isinstance(client_roles, list):
                    roles.update(r.lower() for r in client_roles if isinstance(r, str))

    # Check groups claim (sometimes used for roles)
    if "groups" in payload and isinstance(payload["groups"], list):
        roles.update(g.lower() for g in payload["groups"] if isinstance(g, str))

    # Default roles if none found (fail-open with basic viewer access)
    if not roles:
        logger.info("No roles found in JWT token - granting default 'viewer' role")
        roles.add("viewer")

    logger.debug(f"Extracted roles from token: {roles}")
    return list(roles)


def check_authorization(token: str, required_roles: list[str]) -> None:
    """Check if user has required role(s) to access a tool.

    Args:
        token: JWT bearer token
        required_roles: List of roles (user needs ANY one of these)

    Raises:
        AuthorizationError: If user lacks required roles
    """
    # No role restrictions = allow everyone
    if not required_roles:
        return

    user_roles = get_user_roles(token)

    # Check if user has ANY of the required roles
    user_roles_lower = [r.lower() for r in user_roles]
    required_roles_lower = [r.lower() for r in required_roles]

    if any(role in user_roles_lower for role in required_roles_lower):
        logger.debug(f"Authorization granted: user roles {user_roles} match required {required_roles}")
        return

    # Authorization failed
    logger.warning(
        f"Authorization denied: user roles {user_roles} do not match required {required_roles}"
    )
    raise AuthorizationError(
        f"Insufficient permissions. Required roles: {', '.join(required_roles)}",
        {"user_roles": user_roles, "required_roles": required_roles},
    )
