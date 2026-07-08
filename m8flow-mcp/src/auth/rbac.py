"""Role-Based Access Control (RBAC) for m8flow MCP server.

Extracts user roles from JWT token and validates permissions.

Fail-closed: an undecodable token or a token without any role claims yields
no roles, so any tool that requires roles denies access.

NOTE: This does not verify the token signature — the m8flow backend does full
verification. RBAC here is a coarse pre-filter, not the security boundary.
"""

from __future__ import annotations

from src.auth.jwt_utils import decode_jwt_claims
from src.errors import AuthorizationError
from src.utils.logging import logger


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
        List of role names (lowercase for case-insensitive matching).
        Empty when the token cannot be decoded or carries no role claims
        (fail-closed: no roles are assumed).
    """
    payload = decode_jwt_claims(token)
    if not payload:
        logger.warning("Could not decode JWT token for RBAC - no roles granted")
        return []

    roles: set[str] = set()

    # Check standard "roles" claim
    if isinstance(payload.get("roles"), list):
        roles.update(r.lower() for r in payload["roles"] if isinstance(r, str))

    # Check Keycloak realm roles
    if isinstance(payload.get("realm_access"), dict):
        realm_roles = payload["realm_access"].get("roles", [])
        if isinstance(realm_roles, list):
            roles.update(r.lower() for r in realm_roles if isinstance(r, str))

    # Check Keycloak resource/client roles
    if isinstance(payload.get("resource_access"), dict):
        for access in payload["resource_access"].values():
            if isinstance(access, dict) and isinstance(access.get("roles"), list):
                roles.update(r.lower() for r in access["roles"] if isinstance(r, str))

    # Check groups claim (sometimes used for roles)
    if isinstance(payload.get("groups"), list):
        roles.update(g.lower() for g in payload["groups"] if isinstance(g, str))

    if not roles:
        logger.warning("No roles found in JWT token - access to role-guarded tools will be denied")

    logger.debug(f"Extracted roles from token: {roles}")
    return list(roles)


def check_authorization(token: str, required_roles: list[str]) -> None:
    """Check if user has required role(s) to access a tool.

    Args:
        token: JWT bearer token
        required_roles: List of roles (user needs ANY one of these)

    Raises:
        AuthorizationError: If user lacks required roles (including when the
            token is undecodable or carries no roles — fail-closed)
    """
    # No role restrictions = allow everyone
    if not required_roles:
        return

    user_roles = get_user_roles(token)
    required_roles_lower = [r.lower() for r in required_roles]

    if any(role in user_roles for role in required_roles_lower):
        logger.debug(f"Authorization granted: user roles {user_roles} match required {required_roles}")
        return

    logger.warning(f"Authorization denied: user roles {user_roles} do not match required {required_roles}")
    raise AuthorizationError(
        f"Insufficient permissions. Required roles: {', '.join(required_roles)}",
        {"user_roles": user_roles, "required_roles": required_roles},
    )
