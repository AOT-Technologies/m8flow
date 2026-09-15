"""PKCS#12 client-assertion JWT and master-realm admin token.

The provider owns Keycloak client authentication.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
import warnings

import jwt
import requests

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable
from m8flow_backend.integrations.auth.keycloak.settings import (
    keycloak_admin_password,
    keycloak_admin_user,
    keycloak_url,
    spoke_client_id,
    spoke_keystore_p12_path,
    spoke_keystore_password,
)

logger = logging.getLogger(__name__)

# Cache fetch_master_admin_token()'s result for (most of) its own lifetime.
# Every call site in services/tenant_role_service.py used to fetch this token
# once per top-level operation and thread it through every nested Keycloak
# Admin API call by hand, specifically to avoid re-authenticating dozens of
# times per request (auth-provider-seam wayfinder map, ticket 07's audit).
# Caching it here gives every caller -- that manual threading, and any future
# capability call that doesn't thread a token at all -- the same benefit
# without any signature changes, the same idiom as keycloak/settings.py's
# configure/current_settings and keycloak/jwks.py's JWKS cache.
_MASTER_ADMIN_TOKEN_SAFETY_MARGIN_SECONDS = 10
_MASTER_ADMIN_TOKEN_DEFAULT_TTL_SECONDS = 55  # used when the response omits expires_in
_master_admin_token_lock = threading.Lock()
_cached_master_admin_token: str | None = None
_cached_master_admin_token_expires_at: float | None = None


def reset_master_admin_token_cache() -> None:
    """Drop the cached master admin token. Test-only, mirroring
    reset_jwks_cache()/reset_keycloak_settings()."""
    global _cached_master_admin_token, _cached_master_admin_token_expires_at
    with _master_admin_token_lock:
        _cached_master_admin_token = None
        _cached_master_admin_token_expires_at = None


def load_spoke_p12_private_key():
    """Load the private key (and cert) from the configured PKCS#12 keystore."""
    path = spoke_keystore_p12_path()
    if not path:
        raise ValueError(
            "M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12 path is not set or the file was not found. "
            "Set M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12 to m8flow-backend/keystore.p12 "
            "(or an absolute path) for spoke tenant auth."
        )
    password = spoke_keystore_password()
    if not password:
        raise ValueError("M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD must be set for JWT client assertion.")
    from cryptography.hazmat.primitives.serialization import pkcs12

    with open(path, "rb") as handle:
        data = handle.read()
    password_bytes = password.encode("utf-8") if isinstance(password, str) else password
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="PKCS#12 bundle could not be parsed as DER")
        private_key, certificate, _ = pkcs12.load_key_and_certificates(data, password_bytes)
    if private_key is None:
        raise ValueError("keystore.p12 has no private key")
    return private_key, certificate


def spoke_certificate_pem() -> str:
    """Public certificate PEM from the PKCS#12 keystore (JWT client auth)."""
    _, certificate = load_spoke_p12_private_key()
    if certificate is None:
        raise ValueError("keystore.p12 has no certificate")
    from cryptography.hazmat.primitives.serialization import Encoding

    return certificate.public_bytes(Encoding.PEM).decode("utf-8")


def build_client_assertion_jwt(token_url: str, realm: str) -> str:
    """RFC 7523 client_assertion JWT, signed with the spoke keystore private key."""
    base_url = keycloak_url()
    realm_issuer = f"{base_url}/realms/{realm}"
    client_id = spoke_client_id()
    now = int(time.time())
    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": realm_issuer,
        "exp": now + 60,
        "iat": now,
        "jti": f"{uuid.uuid4().hex}-{now}-{uuid.uuid4().hex[:8]}",
    }
    private_key, _ = load_spoke_p12_private_key()
    return jwt.encode(payload, private_key, algorithm="RS256")


def fetch_master_admin_token() -> str:
    """Cached access token via master-realm admin username/password (Admin API).

    Reuses one token across calls until shortly before it expires (§0 above);
    a cache miss falls through to _fetch_master_admin_token_uncached()."""
    global _cached_master_admin_token, _cached_master_admin_token_expires_at
    now = time.monotonic()
    with _master_admin_token_lock:
        if _cached_master_admin_token is not None and _cached_master_admin_token_expires_at is not None:
            if _cached_master_admin_token_expires_at > now:
                return _cached_master_admin_token

    token, expires_in = _fetch_master_admin_token_uncached()
    ttl = (expires_in if isinstance(expires_in, (int, float)) and expires_in > 0 else None) or (
        _MASTER_ADMIN_TOKEN_DEFAULT_TTL_SECONDS
    )
    ttl = max(1, ttl - _MASTER_ADMIN_TOKEN_SAFETY_MARGIN_SECONDS)
    with _master_admin_token_lock:
        _cached_master_admin_token = token
        _cached_master_admin_token_expires_at = now + ttl
    return token


def _fetch_master_admin_token_uncached() -> tuple[str, int | None]:
    """Access token via master-realm admin username/password (Admin API).
    Returns (access_token, expires_in) -- expires_in may be absent."""
    url = f"{keycloak_url()}/realms/master/protocol/openid-connect/token"
    password = keycloak_admin_password()
    if not password:
        raise ValueError(
            "KEYCLOAK_ADMIN_PASSWORD or M8FLOW_KEYCLOAK_ADMIN_PASSWORD must be set for realm creation."
        )
    username = keycloak_admin_user()
    data = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": username,
        "password": password,
    }
    try:
        response = requests.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["access_token"], payload.get("expires_in")
    except requests.RequestException as exc:
        raise ProviderUnavailable("Could not obtain Keycloak master admin token") from exc
