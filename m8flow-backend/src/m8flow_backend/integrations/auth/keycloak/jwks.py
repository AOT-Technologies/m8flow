"""Backward-compatible entry points for Keycloak token verification.

``verify_access_token``/``reset_jwks_cache`` used to own the JWKS fetch/
cache/verify pipeline directly; that pipeline is now
``base.oidc.OidcClient`` (auth-provider-seam wayfinder map, ticket 04),
realized here as ``keycloak.oidc.oidc_client``. Both names are kept exactly
as they were -- same signatures, same process-wide cache -- so every
existing caller (production and test) is unaffected by the hoist.
"""
from __future__ import annotations

from typing import Any

# Kept importable (not used directly below) so existing tests that
# monkeypatch "keycloak.jwks.requests.get" keep resolving -- the actual GET
# now happens in base/oidc.py's OidcClient._load_jwks, but `requests` is one
# process-wide module object: patching .get here mutates the same function
# object base/oidc.py calls.
import requests  # noqa: F401

from m8flow_backend.integrations.auth.keycloak.oidc import oidc_client


def reset_jwks_cache() -> None:
    oidc_client.reset_cache()


def verify_access_token(token: str) -> dict[str, Any]:
    return oidc_client.verify_access_token(token)
