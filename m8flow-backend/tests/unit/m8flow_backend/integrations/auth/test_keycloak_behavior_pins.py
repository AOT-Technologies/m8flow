"""Characterization pins for the Keycloak auth provider (authProvider-analysis
redesign, Phase 0).

Recorded from the provider *before* the AuthService/trust-domain refactor so
the refactor can prove it did not change existing auth behaviour. Every
assertion here describes what the code did at recording time -- including
the permissive legacy issuer/audience rules, which stay the default until the
opt-in strict mode (``M8FLOW_AUTH_STRICT_ISSUERS``) is switched on.

Do not "fix" an expectation in this file to make a refactor pass: a failing
pin means the refactor changed observable auth behaviour.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from m8flow_backend.integrations.auth.base.models import IssuerRef, VerifiedClaims
from m8flow_backend.integrations.auth.keycloak.claims import verified_claims_from_payload
from m8flow_backend.integrations.auth.keycloak.jwks import reset_jwks_cache
from m8flow_backend.integrations.auth.keycloak.oidc import oidc_client
from m8flow_backend.integrations.auth.keycloak.provider import KeycloakAuthProvider
from m8flow_backend.integrations.auth.keycloak.settings import KeycloakSettings, reset_keycloak_settings

_GOLDEN = Path(__file__).resolve().parents[4] / "fixtures" / "auth" / "keycloak_claims_golden.json"
_INTERNAL = "http://keycloak.internal"
_PUBLIC = "http://keycloak.public"
_CLIENT_ID = "m8flow-backend"


def _settings() -> KeycloakSettings:
    return KeycloakSettings(
        keycloak_url=_INTERNAL,
        keycloak_public_issuer_base=_PUBLIC,
        keycloak_admin_user="admin",
        keycloak_admin_password="admin-pw",
        shared_realm_name="m8flow",
        shared_realm_label="M8Flow Realm",
        default_organization_alias="m8flow",
        default_organization_name="m8flow",
        master_realm_name="master",
        realm_template_path="/dev/null",
        keycloak_default_groups_path="/dev/null",
        spoke_keystore_p12_path=None,
        spoke_keystore_password="",
        spoke_client_id=_CLIENT_ID,
        spoke_client_secret="test-secret",
        master_client_secret="test-secret",
        template_realm_name="m8flow",
    )


@pytest.fixture
def provider():
    reset_keycloak_settings()
    reset_jwks_cache()
    yield KeycloakAuthProvider(_settings())
    reset_keycloak_settings()
    reset_jwks_cache()


def _project(actual: object, expected: object) -> object:
    """Keep only the keys the golden file recorded, so fields added later
    with neutral defaults (trust domain, completeness flags, ...) don't
    register as behaviour changes -- only recorded values can."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return {key: _project(actual.get(key), value) for key, value in expected.items()}
    if isinstance(expected, list) and isinstance(actual, list) and len(actual) == len(expected):
        return [_project(a, e) for a, e in zip(actual, expected)]
    return actual


def _golden_cases() -> list[dict]:
    return json.loads(_GOLDEN.read_text())


@pytest.mark.parametrize("case", _golden_cases(), ids=lambda case: case["name"])
def test_keycloak_claims_mapping_matches_recorded_golden_output(case):
    claims = verified_claims_from_payload(case["payload"])
    actual = dataclasses.asdict(claims)
    actual.pop("jwt_claims")
    assert _project(actual, case["expected"]) == case["expected"]
    assert claims.jwt_claims == case["payload"]


@pytest.mark.parametrize("case", _golden_cases(), ids=lambda case: case["name"])
def test_provider_map_claims_matches_recorded_golden_output(provider, case):
    claims = provider.map_claims(case["payload"])
    actual = dataclasses.asdict(claims)
    actual.pop("jwt_claims")
    assert _project(actual, case["expected"]) == case["expected"]


@pytest.mark.parametrize(
    ("issuer", "jwt_claims", "expected"),
    [
        (f"{_PUBLIC}/realms/master", {}, True),
        (f"{_INTERNAL}/realms/master", {}, True),
        # Deliberately changed: only the verified ``iss`` decides; realm-name
        # claims are mapper output a realm admin controls.
        (f"{_PUBLIC}/realms/m8flow", {"m8flow_authentication_identifier": "master"}, False),
        (f"{_PUBLIC}/realms/m8flow", {"m8flow_realm_name": "master"}, False),
        (f"{_PUBLIC}/realms/m8flow", {}, False),
        (f"{_PUBLIC}/realms/m8flow", {"m8flow_authentication_identifier": "m8flow"}, False),
        ("local", {}, False),
        ("", {}, False),
    ],
)
def test_is_master_issuer_pins(provider, issuer, jwt_claims, expected):
    claims = VerifiedClaims(subject="s", issuer=issuer, jwt_claims=jwt_claims)
    assert provider.is_master_issuer(claims) is expected


@pytest.mark.parametrize(
    ("issuer", "expected"),
    [
        (f"{_PUBLIC}/realms/m8flow", True),
        (f"{_INTERNAL}/realms/m8flow", True),
        (f"{_PUBLIC}/realms/m8flow/", True),
        (f"{_PUBLIC}/realms/master", True),
        # Legacy default: any realm on the configured Keycloak host is trusted.
        # Strict mode (opt-in) narrows this; the default must not change.
        (f"{_PUBLIC}/realms/some-other-realm", True),
        ("http://evil.example/realms/m8flow", False),
        (f"{_PUBLIC}/not-a-realm-path", False),
        ("https://tenant.auth0.com/", False),
    ],
)
def test_default_issuer_trust_pins(provider, issuer, expected):
    del provider  # configures the process-wide settings the client reads
    assert oidc_client._issuer_and_realm_allowed(issuer) is expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"azp": _CLIENT_ID}, True),
        ({"aud": _CLIENT_ID}, True),
        ({"aud": "account"}, True),
        ({"aud": ["other", "account"]}, True),
        ({"aud": ["other", _CLIENT_ID]}, True),
        ({}, True),
        ({"aud": "other"}, False),
        ({"azp": "other"}, False),
        ({"aud": ["other"], "azp": "other"}, False),
    ],
)
def test_default_audience_pins(provider, payload, expected):
    del provider
    assert oidc_client.audience_is_allowed(payload) is expected


def test_login_url_shape_is_pinned(provider):
    url = provider.build_login_url(
        redirect_uri="https://app.example/cb",
        state="abc",
        issuer=IssuerRef(value="m8flow"),
        nonce="n-1",
        prompt="login",
    )
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == f"{_PUBLIC}/realms/m8flow/protocol/openid-connect/auth"
    assert parse_qs(parsed.query) == {
        "client_id": [_CLIENT_ID],
        "redirect_uri": ["https://app.example/cb"],
        "response_type": ["code"],
        "scope": ["openid email profile"],
        "state": ["abc"],
        "prompt": ["login"],
    }


def test_login_url_without_prompt_omits_it(provider):
    url = provider.build_login_url(redirect_uri="https://app.example/cb", state="abc", issuer=IssuerRef(value="m8flow"))
    assert "prompt" not in parse_qs(urlparse(url).query)


def test_logout_url_shapes_are_pinned(provider):
    issuer = IssuerRef(value="m8flow")
    bare = provider.build_logout_url(issuer=issuer)
    assert bare == f"{_PUBLIC}/realms/m8flow/protocol/openid-connect/logout"
    full = provider.build_logout_url(issuer=issuer, redirect_uri="https://app.example/", id_token_hint="idt")
    assert parse_qs(urlparse(full).query) == {
        "id_token_hint": ["idt"],
        "post_logout_redirect_uri": ["https://app.example/"],
    }


def test_self_description_pins(provider):
    assert provider.default_issuer() == IssuerRef(value="m8flow")
    assert provider.default_tenant_ref().alias == "m8flow"
    assert provider.default_issuer_claim() == f"{_PUBLIC}/realms/m8flow"
    assert provider.authorization_endpoint_url(IssuerRef(value="master")) == (
        f"{_PUBLIC}/realms/master/protocol/openid-connect/auth"
    )
