"""Spec-defined OIDC engine (RFC 6749 / RFC 7517 / OIDC Core), hoisted out of
``keycloak/oidc.py`` + ``keycloak/jwks.py`` (auth-provider-seam wayfinder
map, ticket 04) so a second provider doesn't have to re-type discovery/JWKS
caching, RS256 verification, or the authorization-code/refresh token-endpoint
grants -- the same document any OIDC-compliant IdP implements.

``OidcClient`` owns everything spec-defined. A provider subclasses it and
overrides the hook methods below (URL templating, issuer/audience
allow-listing, client authentication) for whatever is genuinely
vendor-specific about its deployment -- see ``keycloak/oidc.py`` for the
worked example, which shrinks to realm-URL templating plus Keycloak's own
issuer/audience rules once this lands.

``OidcAuthProvider`` wraps an ``OidcClient`` to implement ``AuthProvider``'s
five session/verify methods (``build_login_url``, ``exchange_code``,
``refresh``, ``build_logout_url``, ``verify_token``), leaving
``map_claims(payload) -> VerifiedClaims`` abstract -- every provider's
claims-mapping (organization claims, role translation, ...) is genuinely its
own.

Pure extraction: this is a direct line-for-line move of the pre-hoist
Keycloak adapter's spec-defined logic, not a redesign of the verification
pipeline. Ticket 04's own acceptance criterion is mechanical --
``test_jwks.py`` must keep passing with zero edits.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlencode

import jwt
import requests
from jwt.algorithms import RSAAlgorithm

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, TokenInvalid
from m8flow_backend.integrations.auth.base.models import IssuerRef, TokenSet, VerifiedClaims
from m8flow_backend.integrations.auth.base.provider import AuthProvider

logger = logging.getLogger(__name__)

JWKS_CACHE_TTL_SECONDS = 600
SUPPORTED_ALGS = ("RS256",)
_HTTP_TIMEOUT_SECONDS = 10
_TOKEN_TIMEOUT_SECONDS = 30


class OidcClient(ABC):
    """Generic OIDC discovery/JWKS/token-endpoint engine.

    Every method below the "hooks" divider is spec-defined and shared by
    every provider; do not override it. Every method above the divider is a
    hook a subclass must (or, for ``internalize_url``, may) implement --
    that's the entire vendor-specific surface this class exposes.
    """

    def __init__(self) -> None:
        self._cache_lock = threading.Lock()
        self._jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # --- hooks: override in a provider subclass -----------------------------

    @abstractmethod
    def discovery_url(self, realm: str) -> str:
        """Container-internal OpenID discovery document URL for ``realm``."""
        ...

    @abstractmethod
    def token_url(self, realm: str) -> str:
        """Container-internal token endpoint URL for ``realm``."""
        ...

    @abstractmethod
    def authorization_endpoint(self, realm: str) -> str:
        """Browser-facing authorization endpoint URL for ``realm``, no query."""
        ...

    @abstractmethod
    def logout_endpoint(self, realm: str) -> str:
        """Browser-facing RP-initiated logout URL for ``realm``, no query."""
        ...

    def internalize_url(self, url: str) -> str:
        """Rewrite a public-facing URL (e.g. a discovery document's
        ``jwks_uri``) to whatever base this client should actually fetch it
        from. Identity by default -- override only if your deployment splits
        a public base from a container-internal one (Keycloak's Docker
        quirk; not part of the OIDC spec)."""
        return url

    @abstractmethod
    def realm_from_issuer(self, issuer: str) -> str | None:
        """Extract this provider's routing key (Keycloak: realm name) from
        a verified ``iss`` claim, or ``None`` if it isn't shaped like one."""
        ...

    @abstractmethod
    def issuer_is_allowed(self, issuer: str, *, realm: str) -> bool:
        """Whether ``issuer`` is a trusted issuer for ``realm``."""
        ...

    @abstractmethod
    def audience_is_allowed(self, payload: dict[str, Any]) -> bool:
        """Whether a verified token payload's audience/``azp`` names a
        client this provider accepts."""
        ...

    @abstractmethod
    def client_id(self) -> str:
        """This provider's OAuth client_id, for authorization-URL building
        and as part of ``client_auth_params``."""
        ...

    @abstractmethod
    def client_auth_params(self) -> dict[str, str]:
        """Extra client-authentication form fields for a token-endpoint
        POST. Only ``client_secret_post`` is hoisted here (the one strategy
        with a live caller) -- a provider needing ``private_key_jwt`` or
        another RFC 7521/7523 strategy overrides this."""
        ...

    # --- JWKS: fetch/cache/verify -- spec-defined, do not override ----------

    def reset_cache(self) -> None:
        with self._cache_lock:
            self._jwks_cache.clear()

    def _load_jwks(self, realm: str, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        with self._cache_lock:
            cached = self._jwks_cache.get(realm)
            if cached is not None and not force:
                expires_at, jwks = cached
                if expires_at > now:
                    return jwks
        try:
            discovery = requests.get(self.discovery_url(realm), timeout=_HTTP_TIMEOUT_SECONDS)
            discovery.raise_for_status()
            document = discovery.json()
            jwks_uri = document.get("jwks_uri")
            if not isinstance(jwks_uri, str) or not jwks_uri:
                raise ProviderUnavailable(f"OpenID discovery for realm {realm!r} omitted jwks_uri")
            jwks_response = requests.get(self.internalize_url(jwks_uri), timeout=_HTTP_TIMEOUT_SECONDS)
            jwks_response.raise_for_status()
            jwks = jwks_response.json()
        except TokenInvalid:
            raise
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable(f"Could not fetch JWKS for realm {realm!r}") from exc
        if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
            raise ProviderUnavailable(f"JWKS for realm {realm!r} is malformed")
        with self._cache_lock:
            self._jwks_cache[realm] = (now + JWKS_CACHE_TTL_SECONDS, jwks)
        return jwks

    @staticmethod
    def _signing_key(jwks: dict[str, Any], kid: str | None):
        for jwk in jwks.get("keys") or []:
            if not isinstance(jwk, dict):
                continue
            if kid is not None and jwk.get("kid") != kid:
                continue
            if jwk.get("kty") != "RSA":
                continue
            return RSAAlgorithm.from_jwk(json.dumps(jwk))
        return None

    def verify_access_token(self, token: str) -> dict[str, Any]:
        """Verify signature (JWKS), issuer, audience, and expiry. Return the
        payload. Spec-defined pipeline; ``realm_from_issuer``/
        ``issuer_is_allowed``/``audience_is_allowed`` are the only
        vendor-shaped decisions inside it."""
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
        except jwt.PyJWTError as exc:
            raise TokenInvalid("Token is malformed") from exc

        issuer = unverified.get("iss")
        if not isinstance(issuer, str) or not self._issuer_and_realm_allowed(issuer):
            raise TokenInvalid("Token issuer is not a configured Keycloak realm")

        realm = self.realm_from_issuer(issuer)
        if realm is None:
            raise TokenInvalid("Token issuer is missing a realm")

        alg = header.get("alg")
        if alg not in SUPPORTED_ALGS:
            raise TokenInvalid(f"Unsupported token algorithm {alg!r}")

        kid = header.get("kid") if isinstance(header.get("kid"), str) else None
        jwks = self._load_jwks(realm)
        key = self._signing_key(jwks, kid)
        if key is None:
            jwks = self._load_jwks(realm, force=True)
            key = self._signing_key(jwks, kid)
        if key is None:
            raise TokenInvalid("Token signing key was not found in JWKS")

        try:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=list(SUPPORTED_ALGS),
                options={"require": ["exp", "iss"], "verify_aud": False},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenInvalid("Token has expired") from exc
        except jwt.InvalidIssuerError as exc:
            raise TokenInvalid("Token issuer is invalid") from exc
        except jwt.PyJWTError as exc:
            raise TokenInvalid("Token signature verification failed") from exc

        if not self.audience_is_allowed(payload):
            raise TokenInvalid("Token audience does not match the configured client")

        # jwt.decode does not re-check iss against our allow-list (verify_aud
        # is disabled, and issuer= isn't passed since public vs. internal
        # bases both occur). Repeat the check on the verified payload.
        verified_iss = payload.get("iss")
        if not isinstance(verified_iss, str) or not self._issuer_and_realm_allowed(verified_iss):
            raise TokenInvalid("Token issuer is not a configured Keycloak realm")
        return payload

    def _issuer_and_realm_allowed(self, issuer: str) -> bool:
        realm = self.realm_from_issuer(issuer)
        if not realm:
            return False
        return self.issuer_is_allowed(issuer, realm=realm)

    # --- token endpoint: authorization_code / refresh grants ----------------

    def _post_token(self, realm: str, data: dict[str, str], *, failure_log: str) -> TokenSet:
        url = self.token_url(realm)
        try:
            response = requests.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=_TOKEN_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise ProviderUnavailable(f"OIDC {failure_log} request failed") from exc
        if not response.ok:
            logger.warning(
                "OIDC %s failed: realm=%s status=%s body=%s",
                failure_log,
                realm,
                response.status_code,
                response.text[:500],
            )
            raise TokenInvalid(f"OIDC {failure_log} was rejected")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TokenInvalid(f"OIDC {failure_log} returned non-JSON") from exc
        if not isinstance(payload, dict):
            raise TokenInvalid(f"OIDC {failure_log} returned an unexpected payload")
        return self._token_set_from_response(payload)

    @staticmethod
    def _token_set_from_response(payload: dict[str, Any]) -> TokenSet:
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise TokenInvalid("OIDC provider did not return an access token")
        expires_in = payload.get("expires_in")
        refresh_expires_in = payload.get("refresh_expires_in")
        return TokenSet(
            access_token=access_token,
            refresh_token=payload.get("refresh_token") if isinstance(payload.get("refresh_token"), str) else None,
            id_token=payload.get("id_token") if isinstance(payload.get("id_token"), str) else None,
            expires_in=int(expires_in) if expires_in is not None else None,
            refresh_expires_in=int(refresh_expires_in) if refresh_expires_in is not None else None,
        )

    def exchange_authorization_code(self, *, realm: str, code: str, redirect_uri: str) -> TokenSet:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            **self.client_auth_params(),
        }
        return self._post_token(realm, data, failure_log="authorization-code exchange")

    def refresh_tokens(self, *, realm: str, refresh_token: str) -> TokenSet:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            **self.client_auth_params(),
        }
        return self._post_token(realm, data, failure_log="refresh")

    # --- authorization / logout URL building --------------------------------

    def build_authorization_url(self, *, realm: str, redirect_uri: str, state: str, prompt: str | None = None) -> str:
        params: dict[str, str] = {
            "client_id": self.client_id(),
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
        if prompt:
            params["prompt"] = prompt
        return f"{self.authorization_endpoint(realm)}?{urlencode(params)}"

    def build_logout_url(self, *, realm: str, redirect_uri: str | None = None, id_token_hint: str | None = None) -> str:
        params: dict[str, str] = {}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        if redirect_uri:
            params["post_logout_redirect_uri"] = redirect_uri
        if not params:
            return self.logout_endpoint(realm)
        return f"{self.logout_endpoint(realm)}?{urlencode(params)}"


class OidcAuthProvider(AuthProvider):
    """``AuthProvider`` realized on top of an ``OidcClient``. Subclass and
    implement ``map_claims`` (translate a verified payload into
    ``VerifiedClaims``) plus whatever self-description/directory/capability
    methods your provider needs -- every session/verify method is already
    handled here."""

    def __init__(self, client: OidcClient) -> None:
        self._oidc = client

    def build_login_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        issuer: IssuerRef,
        nonce: str | None = None,
        prompt: str | None = None,
    ) -> str:
        del nonce  # stored by the host in state/cookie; not sent to the IdP today
        return self._oidc.build_authorization_url(realm=issuer.value, redirect_uri=redirect_uri, state=state, prompt=prompt)

    def exchange_code(self, *, code: str, redirect_uri: str, issuer: IssuerRef) -> TokenSet:
        return self._oidc.exchange_authorization_code(realm=issuer.value, code=code, redirect_uri=redirect_uri)

    def refresh(self, *, refresh_token: str, issuer: IssuerRef) -> TokenSet:
        return self._oidc.refresh_tokens(realm=issuer.value, refresh_token=refresh_token)

    def build_logout_url(
        self,
        *,
        issuer: IssuerRef,
        redirect_uri: str | None = None,
        id_token_hint: str | None = None,
    ) -> str:
        return self._oidc.build_logout_url(realm=issuer.value, redirect_uri=redirect_uri, id_token_hint=id_token_hint)

    def verify_token(self, token: str) -> VerifiedClaims:
        payload = self._oidc.verify_access_token(token)
        try:
            return self.map_claims(payload)
        except ValueError as exc:
            raise TokenInvalid(str(exc)) from exc

    @abstractmethod
    def map_claims(self, payload: dict[str, Any]) -> VerifiedClaims:
        """Translate a verified token payload into ``VerifiedClaims``. Every
        provider's own vocabulary (organization claims, group-to-role
        translation, ...) lives here, never in ``OidcClient``."""
        ...
