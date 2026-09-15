"""KeycloakAuthProvider runs the AuthProvider conformance suite (auth-provider-
seam wayfinder map, ticket 02) -- the second implementation proving
``testing/conformance.py`` asserts the port's contract, not
``InMemoryAuthProvider``'s shape.

``_FakeKeycloakServer`` stands in for Keycloak's HTTP surface (discovery,
JWKS, the token endpoint, and the one Admin API user/attribute round trip
``set_active_tenant`` needs), the same style ``test_jwks.py``/
``test_directory.py`` already use elsewhere in this package -- nothing here
talks to a real Keycloak. The master-realm admin token fetch itself is
monkeypatched away entirely (``test_directory.py``'s existing pattern),
since exercising it isn't this suite's job.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import jwt
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable
from m8flow_backend.integrations.auth.base.provider import AuthProvider
from m8flow_backend.integrations.auth.keycloak.jwks import reset_jwks_cache
from m8flow_backend.integrations.auth.keycloak.provider import KeycloakAuthProvider
from m8flow_backend.integrations.auth.keycloak.settings import KeycloakSettings, reset_keycloak_settings
from m8flow_backend.integrations.auth.testing.conformance import AuthProviderConformance

_INTERNAL_BASE = "http://keycloak.internal"
_PUBLIC_BASE = "http://keycloak.public"
_REALM = "m8flow"
_CLIENT_ID = "m8flow-backend"


def _public_jwk(private_key) -> dict[str, Any]:
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = "test-kid"
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return jwk


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(f"http {self.status_code}")

    def json(self):
        return self._payload


class _FakeKeycloakServer:
    """In-memory stand-in for the slice of Keycloak's HTTP surface the
    conformance suite's scenarios touch. Not a general-purpose Keycloak
    mock -- just enough to prove KeycloakAuthProvider satisfies the same
    contract InMemoryAuthProvider does."""

    def __init__(self) -> None:
        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._jwk = _public_jwk(self._private_key)
        self.discovery_url = f"{_INTERNAL_BASE}/realms/{_REALM}/.well-known/openid-configuration"
        self.jwks_url = f"{_INTERNAL_BASE}/realms/{_REALM}/protocol/openid-connect/certs"
        self.token_url = f"{_INTERNAL_BASE}/realms/{_REALM}/protocol/openid-connect/token"
        self.users_url = f"{_INTERNAL_BASE}/admin/realms/{_REALM}/users"
        self.users: dict[str, dict[str, Any]] = {}
        self.codes: dict[str, str] = {}
        self.refresh_tokens: dict[str, str] = {}

    # --- harness / seeding hooks -----------------------------------------

    def register_user(self, username: str) -> str:
        subject = f"subject-{len(self.users) + 1}"
        self.users[username] = {"id": subject, "attributes": {}}
        return subject

    def issue_authorization_code(self, username: str) -> str:
        if username not in self.users:
            self.register_user(username)
        code = f"code-{uuid.uuid4().hex}"
        self.codes[code] = username
        return code

    def mint_jwt(
        self,
        username: str,
        *,
        exp_delta: int = 3600,
        iss: str | None = None,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        if username not in self.users:
            self.register_user(username)
        subject = self.users[username]["id"]
        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": subject,
            "iss": iss if iss is not None else f"{_PUBLIC_BASE}/realms/{_REALM}",
            "azp": _CLIENT_ID,
            "preferred_username": username,
            "iat": now,
            "exp": now + exp_delta,
        }
        active_tenant = self.users[username]["attributes"].get("m8flow_active_tenant")
        if active_tenant:
            payload["m8flow_tenant_id"] = active_tenant
        if extra_claims:
            payload.update(extra_claims)
        return jwt.encode(payload, self._private_key, algorithm="RS256", headers={"kid": "test-kid"})

    # --- fake HTTP layer -----------------------------------------------------

    def fake_get(self, url, *, params=None, timeout=None, headers=None):
        if url == self.discovery_url:
            return _FakeResponse({"jwks_uri": self.jwks_url})
        if url == self.jwks_url:
            return _FakeResponse({"keys": [self._jwk]})
        if url == self.users_url:
            username = (params or {}).get("username")
            representation = self.users.get(username)
            if representation is None:
                return _FakeResponse([])
            attributes = {key: [value] for key, value in representation["attributes"].items()}
            return _FakeResponse([{"id": representation["id"], "username": username, "attributes": attributes}])
        raise AssertionError(f"unexpected GET {url}")

    def fake_put(self, url, *, json=None, headers=None, timeout=None):
        prefix = f"{self.users_url}/"
        if url.startswith(prefix):
            user_id = url[len(prefix) :]
            username = next((u for u, rep in self.users.items() if rep["id"] == user_id), None)
            if username is None:
                return _FakeResponse({}, status_code=404)
            raw_attributes = (json or {}).get("attributes") or {}
            self.users[username]["attributes"] = {
                key: (value[0] if isinstance(value, list) and value else "") for key, value in raw_attributes.items()
            }
            return _FakeResponse({}, status_code=204)
        raise AssertionError(f"unexpected PUT {url}")

    def fake_post(self, url, *, data=None, json=None, headers=None, timeout=None):
        if url != self.token_url:
            raise AssertionError(f"unexpected POST {url}")
        data = data or {}
        grant_type = data.get("grant_type")
        username = None
        if grant_type == "authorization_code":
            username = self.codes.pop(data.get("code"), None)
        elif grant_type == "refresh_token":
            username = self.refresh_tokens.get(data.get("refresh_token"))
        if username is None:
            return _FakeResponse({"error": "invalid_grant"}, status_code=400)
        access_token = self.mint_jwt(username)
        refresh_token = f"refresh-{uuid.uuid4().hex}"
        self.refresh_tokens[refresh_token] = username
        return _FakeResponse(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "id_token": access_token,
                "expires_in": 3600,
            }
        )


def _settings() -> KeycloakSettings:
    return KeycloakSettings(
        keycloak_url=_INTERNAL_BASE,
        keycloak_public_issuer_base=_PUBLIC_BASE,
        keycloak_admin_user="admin",
        keycloak_admin_password="admin-pw",
        shared_realm_name=_REALM,
        shared_realm_label="M8Flow Realm",
        default_organization_alias=_REALM,
        default_organization_name=_REALM,
        master_realm_name="master",
        realm_template_path="/dev/null",
        keycloak_default_groups_path="/dev/null",
        spoke_keystore_p12_path=None,
        spoke_keystore_password="",
        spoke_client_id=_CLIENT_ID,
        spoke_client_secret="test-secret",
        master_client_secret="test-secret",
        template_realm_name=_REALM,
    )


class TestKeycloakAuthProviderConformance(AuthProviderConformance):
    # KeycloakAuthProvider supports every capability -- nothing declined.
    declined_capabilities = frozenset()

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        reset_keycloak_settings()
        reset_jwks_cache()
        self.server = _FakeKeycloakServer()
        monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.oidc.requests.post", self.server.fake_post)
        monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.jwks.requests.get", self.server.fake_get)
        monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", self.server.fake_get)
        monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.put", self.server.fake_put)
        monkeypatch.setattr(
            "m8flow_backend.integrations.auth.keycloak.admin_client.fetch_master_admin_token",
            lambda: "fake-admin-token",
        )
        yield
        reset_keycloak_settings()
        reset_jwks_cache()

    def build_provider(self) -> AuthProvider:
        return KeycloakAuthProvider(_settings())

    def issue_authorization_code(self, *, username: str) -> str:
        return self.server.issue_authorization_code(username)

    def tampered_access_token(self, *, username: str) -> str:
        token = self.server.mint_jwt(username)
        # Flip a character in the middle of the token, not the last one: the
        # final base64url group of a blob can have "don't care" padding bits
        # a lenient decoder ignores, so a last-character flip is sometimes a
        # no-op on the decoded signature bytes. A middle character sits well
        # inside a full 6-bits-meaningful group, so flipping it always
        # changes the decoded bytes.
        mid = len(token) // 2
        flipped = "y" if token[mid] != "y" else "z"
        return token[:mid] + flipped + token[mid + 1 :]

    def expired_access_token(self, *, username: str) -> str:
        return self.server.mint_jwt(username, exp_delta=-10)

    def wrong_issuer_access_token(self, *, username: str) -> str:
        return self.server.mint_jwt(username, iss="http://evil.example/realms/m8flow")

    def vendor_only_role_leaf(self) -> str | None:
        # "Administrators" is the Keycloak organization-group name
        # role_mapping.py translates to the neutral "tenant-admin".
        return "Administrators"

    def access_token_with_vendor_role_leaf(self, *, username: str, leaf: str) -> str:
        return self.server.mint_jwt(username, extra_claims={"groups": [f"/{leaf}"]})

    def access_token_with_multiple_memberships(self, *, username: str, tenant_refs) -> str:
        organization = {ref.alias: {"id": ref.id} for ref in tenant_refs}
        return self.server.mint_jwt(username, extra_claims={"organization": organization})

    def trigger_provider_unavailable(self) -> None:
        import m8flow_backend.integrations.auth.keycloak.jwks as jwks_module

        provider = self.build_provider()
        token = self.server.mint_jwt("conformance-user")

        def _broken_get(url, **kwargs):
            raise requests.ConnectionError("simulated network outage")

        original = jwks_module.requests.get
        jwks_module.requests.get = _broken_get
        try:
            with pytest.raises(ProviderUnavailable):
                provider.verify_token(token)
        finally:
            jwks_module.requests.get = original
