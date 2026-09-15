"""Keycloak-specific overrides on top of ``base/oidc.py``'s spec-defined
engine (auth-provider-seam wayfinder map, ticket 04).

Discovery/JWKS fetch+cache, RS256 verification, and the authorization-code/
refresh token-endpoint grants all live in ``base.oidc.OidcClient`` now. Only
what's genuinely Keycloak-specific remains here: realm URL templating, the
public/internal Docker base split (``_internalize_url``), and Keycloak's own
issuer/audience allow-listing rules -- exactly the ~54 lines ticket 04's own
audit found weren't spec-defined.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# Kept importable (not used directly below) so existing tests that
# monkeypatch "keycloak.oidc.requests.post" keep resolving -- the actual
# POST now happens in base/oidc.py's OidcClient._post_token, but `requests`
# is one process-wide module object: patching .post here mutates the same
# function object base/oidc.py calls.
import requests  # noqa: F401

from m8flow_backend.integrations.auth.base.oidc import OidcClient
from m8flow_backend.integrations.auth.keycloak.settings import (
    keycloak_public_issuer_base,
    keycloak_url,
    master_client_secret,
    spoke_client_id,
    spoke_client_secret,
)


class _KeycloakOidcClient(OidcClient):
    """Keycloak's realization of the OIDC hooks. Every method here reads
    settings live (via keycloak/settings.py's accessors), not at
    construction time, so `configure()`/`reset_keycloak_settings()` between
    tests are picked up correctly."""

    def discovery_url(self, realm: str) -> str:
        return f"{keycloak_url().rstrip('/')}/realms/{realm}/.well-known/openid-configuration"

    def token_url(self, realm: str) -> str:
        return f"{keycloak_url()}/realms/{str(realm).strip()}/protocol/openid-connect/token"

    def authorization_endpoint(self, realm: str) -> str:
        if not realm or not str(realm).strip():
            raise ValueError("realm is required")
        return f"{keycloak_public_issuer_base()}/realms/{str(realm).strip()}/protocol/openid-connect/auth"

    def logout_endpoint(self, realm: str) -> str:
        return f"{keycloak_public_issuer_base()}/realms/{str(realm).strip()}/protocol/openid-connect/logout"

    def internalize_url(self, url: str) -> str:
        public = keycloak_public_issuer_base().rstrip("/")
        internal = keycloak_url().rstrip("/")
        if public and url.startswith(public):
            return internal + url[len(public):]
        return url

    def realm_from_issuer(self, issuer: str) -> str | None:
        parsed = urlparse(issuer)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "realms":
            return parts[1]
        return None

    def issuer_is_allowed(self, issuer: str, *, realm: str) -> bool:
        allowed = {
            f"{keycloak_public_issuer_base().rstrip('/')}/realms/{realm}",
            f"{keycloak_url().rstrip('/')}/realms/{realm}",
        }
        return issuer.rstrip("/") in allowed

    def audience_is_allowed(self, payload: dict[str, Any]) -> bool:
        client_id = spoke_client_id()
        azp = payload.get("azp")
        aud = payload.get("aud")
        if azp == client_id:
            return True
        if isinstance(aud, str) and aud in {client_id, "account"}:
            return True
        if isinstance(aud, list) and (client_id in aud or "account" in aud):
            return True
        if aud is None and azp is None:
            return True
        return False

    def client_id(self) -> str:
        return spoke_client_id()

    def client_auth_params(self) -> dict[str, str]:
        # Prefer the spoke secret when set; otherwise the master secret resolved
        # by KeycloakSettings (required outside unit-testing — no committed fallback).
        from m8flow_backend.startup.env_var_mapper import is_unit_testing_environment

        secret = (spoke_client_secret() or master_client_secret()).strip()
        if not secret and not is_unit_testing_environment():
            raise RuntimeError(
                "OIDC client_secret is not configured. Set "
                "M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET or M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET."
            )
        return {"client_id": spoke_client_id(), "client_secret": secret}


#: Process-wide singleton -- shares one JWKS cache across every call site,
#: exactly as the pre-hoist module-level `_jwks_cache` dict did. Imported by
#: keycloak/jwks.py (verify_access_token/reset_jwks_cache) and
#: keycloak/provider.py (KeycloakAuthProvider's OidcAuthProvider base).
oidc_client = _KeycloakOidcClient()
