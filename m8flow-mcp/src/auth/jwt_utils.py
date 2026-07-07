"""Lightweight JWT helpers for the m8flow MCP server.

These helpers decode a JWT *payload without verifying its signature*. They exist
only to read informational claims (username, tenant id, expiry) for logging and
context setup. For security-critical validation use ``KeycloakAuth`` in
``src/auth/keycloak.py`` (RS256 signature + issuer + audience checks).
"""

from __future__ import annotations

import base64
import json
from typing import Any

# JWT claim carrying the m8flow tenant id. Set by the Keycloak realm-info
# protocol mapper and read by the m8flow backend — keep all readers on this
# single constant (the backend's ``m8f_tenant_id`` is a DB column, not a claim).
TENANT_ID_CLAIM = "m8flow_tenant_id"


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """Decode a JWT payload without verifying the signature.

    Args:
        token: A JWT, optionally prefixed with ``"Bearer "``.

    Returns:
        The decoded claims as a dict, or ``{}`` if the token is malformed.
    """
    raw = token[7:] if token.startswith("Bearer ") else token
    parts = raw.split(".")
    if len(parts) != 3:
        return {}

    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)  # restore base64 padding
    try:
        claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(payload_b64))
        return claims
    except Exception:
        return {}
