"""Keycloak-side behaviour added by the authProvider-analysis redesign: issuer
classification, verification-time stamping, the opt-in strict issuer mode,
the opt-in m8flow contract claim, and the OIDC authorize hooks.

Every opt-in here is off by default; the default behaviour is pinned in
``test_keycloak_behavior_pins.py``.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, TrustDomain, VerifiedClaims
from m8flow_backend.integrations.auth.base.oidc import OidcClient
from m8flow_backend.integrations.auth.core import AuthService
from m8flow_backend.integrations.auth.core.contract import CONTRACT_CLAIMS_ENV, DEFAULT_CONTRACT_CLAIM_KEY
from m8flow_backend.integrations.auth.keycloak.jwks import reset_jwks_cache
from m8flow_backend.integrations.auth.keycloak.oidc import oidc_client
from m8flow_backend.integrations.auth.keycloak.provider import KeycloakAuthProvider
from m8flow_backend.integrations.auth.keycloak.settings import KeycloakSettings, reset_keycloak_settings

_GOLDEN = Path(__file__).resolve().parents[4] / "fixtures" / "auth" / "keycloak_claims_golden.json"
_PUBLIC = "http://keycloak.public"
_INTERNAL = "http://keycloak.internal"
_CLIENT_ID = "m8flow-backend"


def _settings(**overrides) -> KeycloakSettings:
    values = dict(
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
    values.update(overrides)
    return KeycloakSettings(**values)


@pytest.fixture
def make_provider():
    def _make(**overrides) -> KeycloakAuthProvider:
        reset_keycloak_settings()
        return KeycloakAuthProvider(_settings(**overrides))

    reset_jwks_cache()
    yield _make
    reset_keycloak_settings()
    reset_jwks_cache()


# --- issuer classification ---------------------------------------------------


@pytest.mark.parametrize(
    ("issuer", "jwt_claims", "expected"),
    [
        (f"{_PUBLIC}/realms/master", {}, TrustDomain.PLATFORM),
        # A realm-name claim naming master is mapper output, not proof of the issuer.
        (f"{_PUBLIC}/realms/m8flow", {"m8flow_authentication_identifier": "master"}, TrustDomain.SHARED),
        (f"{_PUBLIC}/realms/m8flow", {}, TrustDomain.SHARED),
        (f"{_PUBLIC}/realms/acme-spoke", {}, TrustDomain.TENANT),
        ("local", {}, TrustDomain.SHARED),
    ],
)
def test_keycloak_trust_domain(make_provider, issuer, jwt_claims, expected):
    provider = make_provider()
    assert provider.trust_domain(VerifiedClaims(subject="s", issuer=issuer, jwt_claims=jwt_claims)) is expected


@pytest.mark.parametrize("case", json.loads(_GOLDEN.read_text()), ids=lambda case: case["name"])
def test_platform_session_is_exactly_is_master_issuer(make_provider, case):
    """The equivalence the bind.py rewire relies on: AuthService's platform
    detection never disagrees with the original is_master_issuer, whether
    the claims were stamped at verification or wrapped from a raw payload."""
    provider = make_provider()
    stamped = provider.map_claims(case["payload"])
    raw = VerifiedClaims(subject="s", issuer=case["payload"]["iss"], jwt_claims=case["payload"])
    service = AuthService(provider)
    assert service.is_platform_session(stamped) is provider.is_master_issuer(stamped)
    assert service.is_platform_session(raw) is provider.is_master_issuer(raw)


def test_map_claims_stamps_issuer_key_and_domain(make_provider):
    provider = make_provider()
    claims = provider.map_claims({"sub": "s", "iss": f"{_PUBLIC}/realms/m8flow", "preferred_username": "u"})
    assert claims.issuer_key == "m8flow"
    assert claims.trust_domain is TrustDomain.SHARED
    assert claims.memberships_complete is False


# --- strict issuers (opt-in) -------------------------------------------------


@pytest.mark.parametrize(
    ("issuer", "expected"),
    [
        (f"{_PUBLIC}/realms/m8flow", True),
        (f"{_INTERNAL}/realms/master", True),
        (f"{_PUBLIC}/realms/extra-realm", True),
        (f"{_PUBLIC}/realms/some-other-realm", False),
        ("http://evil.example/realms/m8flow", False),
    ],
)
def test_strict_issuers_trust_only_configured_realms(make_provider, issuer, expected):
    make_provider(strict_issuers=True, trusted_realm_names=("extra-realm",))
    assert oidc_client._issuer_and_realm_allowed(issuer) is expected


def test_strict_issuers_reject_tokens_without_audience(make_provider):
    make_provider(strict_issuers=True)
    assert oidc_client.audience_is_allowed({}) is False
    assert oidc_client.audience_is_allowed({"azp": _CLIENT_ID}) is True
    assert oidc_client.audience_is_allowed({"aud": "account"}) is True


def test_strict_mode_reads_from_env():
    settings = KeycloakSettings.from_env(
        {
            "M8FLOW_BACKEND_ENV": "unit_testing",
            "M8FLOW_AUTH_STRICT_ISSUERS": "true",
            "M8FLOW_KEYCLOAK_TRUSTED_REALMS": " a , b ,,",
        }
    )
    assert settings.strict_issuers is True
    assert settings.trusted_realm_names == ("a", "b")
    defaults = KeycloakSettings.from_env({"M8FLOW_BACKEND_ENV": "unit_testing"})
    assert defaults.strict_issuers is False
    assert defaults.trusted_realm_names == ()


# --- contract claim (opt-in) -------------------------------------------------


def _contract_payload(**claim) -> dict:
    return {
        "sub": "s",
        "iss": f"{_PUBLIC}/realms/m8flow",
        "preferred_username": "editor",
        "realm_access": {"roles": ["offline_access"]},
        "organization": {"legacy": {"id": "legacy-id"}},
        DEFAULT_CONTRACT_CLAIM_KEY: {"v": 1, **claim},
    }


def test_contract_claim_is_ignored_when_flag_is_off(make_provider, monkeypatch):
    monkeypatch.delenv(CONTRACT_CLAIMS_ENV, raising=False)
    provider = make_provider()
    payload = _contract_payload(tenants=[{"tenant": {"id": "t1"}, "roles": ["editor"], "roles_complete": True}])
    claims = provider.map_claims(payload)
    assert [m.tenant_ref.id for m in claims.memberships] == ["legacy-id"]
    assert claims.roles == ["offline_access"]


def test_contract_claim_drives_memberships_when_flag_is_on(make_provider, monkeypatch):
    monkeypatch.setenv(CONTRACT_CLAIMS_ENV, "1")
    provider = make_provider()
    payload = _contract_payload(
        domain="shared",
        active_tenant={"id": "t1", "alias": "acme"},
        tenants=[
            {"tenant": {"id": "t1", "alias": "acme"}, "roles": ["editor"], "groups": ["Designers"], "roles_complete": True},
            {"tenant": {"id": "t2"}, "roles": ["viewer"]},
        ],
        tenants_complete=True,
        platform_roles=["super-admin"],
    )
    claims = provider.map_claims(payload)
    assert claims.memberships == [
        Membership(tenant_ref=TenantRef(id="t1", alias="acme"), roles=["editor"], groups=["Designers"], roles_complete=True),
        Membership(tenant_ref=TenantRef(id="t2"), roles=["viewer"]),
    ]
    assert claims.memberships_complete is True
    assert claims.active_tenant_ref == TenantRef(id="t1", alias="acme")
    # Only the active tenant's roles are merged; platform roles from a SHARED
    # issuer are dropped by the trust policy.
    assert claims.roles == ["offline_access", "editor"]


def test_contract_roles_from_other_tenants_do_not_leak_into_the_active_one(make_provider, monkeypatch):
    monkeypatch.setenv(CONTRACT_CLAIMS_ENV, "1")
    provider = make_provider()
    payload = _contract_payload(
        domain="shared",
        active_tenant={"alias": "beta"},
        tenants=[
            {"tenant": {"id": "t1", "alias": "acme"}, "roles": ["tenant-admin"]},
            {"tenant": {"id": "t2", "alias": "beta"}, "roles": ["viewer"]},
        ],
        tenants_complete=True,
    )
    claims = provider.map_claims(payload)
    assert claims.roles == ["offline_access", "viewer"]
    assert "tenant-admin" not in claims.roles


def test_contract_without_an_active_tenant_merges_no_tenant_roles(make_provider, monkeypatch):
    monkeypatch.setenv(CONTRACT_CLAIMS_ENV, "1")
    provider = make_provider()
    payload = _contract_payload(
        domain="shared",
        tenants=[
            {"tenant": {"id": "t1"}, "roles": ["tenant-admin"]},
            {"tenant": {"id": "t2"}, "roles": ["viewer"]},
        ],
        tenants_complete=True,
    )
    claims = provider.map_claims(payload)
    assert claims.roles == ["offline_access"]


def test_contract_platform_roles_honoured_only_from_platform_issuer(make_provider, monkeypatch):
    monkeypatch.setenv(CONTRACT_CLAIMS_ENV, "1")
    provider = make_provider()
    payload = _contract_payload(domain="platform", platform_roles=["super-admin"])
    payload["iss"] = f"{_PUBLIC}/realms/master"
    claims = provider.map_claims(payload)
    assert "super-admin" in claims.roles
    assert claims.trust_domain is TrustDomain.PLATFORM


def test_contract_domain_mismatch_is_rejected(make_provider, monkeypatch):
    monkeypatch.setenv(CONTRACT_CLAIMS_ENV, "1")
    provider = make_provider()
    with pytest.raises(ValueError, match="does not match"):
        provider.map_claims(_contract_payload(domain="platform"))


def test_contract_absent_falls_back_to_legacy_parsing(make_provider, monkeypatch):
    monkeypatch.setenv(CONTRACT_CLAIMS_ENV, "1")
    provider = make_provider()
    payload = _contract_payload()
    payload.pop(DEFAULT_CONTRACT_CLAIM_KEY)
    golden_free = dataclasses.asdict(provider.map_claims(payload))
    assert [m["tenant_ref"]["id"] for m in golden_free["memberships"]] == ["legacy-id"]


# --- trust policy through verify_token -------------------------------------


class _StubOidc:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def verify_access_token(self, token: str) -> dict:
        return self.payload


def _verify(provider: KeycloakAuthProvider, monkeypatch, payload: dict) -> VerifiedClaims:
    monkeypatch.setattr(provider, "_oidc", _StubOidc(payload))
    return provider.verify_token("token")


@pytest.mark.parametrize(
    ("realm", "extra"),
    [
        ("m8flow", {}),
        ("acme-spoke", {}),
        ("m8flow", {"m8flow_authentication_identifier": "master"}),
    ],
)
def test_non_master_realm_cannot_grant_super_admin(make_provider, monkeypatch, realm, extra):
    payload = {
        "sub": "s",
        "iss": f"{_PUBLIC}/realms/{realm}",
        "roles": ["super-admin"],
        "realm_access": {"roles": ["super-admin"]},
        "groups": ["super-admin"],
        **extra,
    }
    assert "super-admin" not in _verify(make_provider(), monkeypatch, payload).roles


def test_master_realm_super_admin_is_honoured(make_provider, monkeypatch):
    payload = {"sub": "s", "iss": f"{_PUBLIC}/realms/master", "roles": ["super-admin"]}
    assert "super-admin" in _verify(make_provider(), monkeypatch, payload).roles


def test_contract_membership_group_named_super_admin_is_stripped(make_provider, monkeypatch):
    monkeypatch.setenv(CONTRACT_CLAIMS_ENV, "1")
    payload = _contract_payload(
        active_tenant={"id": "t1"},
        tenants=[{"tenant": {"id": "t1"}, "roles": ["editor"], "groups": ["super-admin", "Designers"]}],
    )
    claims = _verify(make_provider(), monkeypatch, payload)
    assert "super-admin" not in claims.roles
    assert claims.memberships == [Membership(tenant_ref=TenantRef(id="t1"), roles=["editor"], groups=["Designers"])]


@pytest.mark.parametrize(("realm", "kept"), [("m8flow", False), ("master", True)])
def test_verify_token_classifies_unstamped_claims_before_enforcing(make_provider, monkeypatch, realm, kept):
    """A provider whose ``map_claims`` leaves ``trust_domain`` unset still gets
    the policy, through its ``trust_domain(claims)`` classifier."""
    provider = make_provider()
    monkeypatch.setattr(provider, "_oidc", _StubOidc({}))
    monkeypatch.setattr(
        provider,
        "map_claims",
        lambda payload: VerifiedClaims(subject="s", issuer=f"{_PUBLIC}/realms/{realm}", roles=["super-admin"]),
    )
    assert ("super-admin" in provider.verify_token("token").roles) is kept


def test_keycloak_reports_every_capability(make_provider):
    assert all(AuthService(make_provider()).capabilities().values())


# --- OIDC hooks ----------------------------------------------------------------


class _HookedClient(OidcClient):
    def discovery_url(self, realm):
        return "https://idp/.well-known/openid-configuration"

    def token_url(self, realm):
        return "https://idp/oauth/token"

    def authorization_endpoint(self, realm):
        return "https://idp/authorize"

    def logout_endpoint(self, realm):
        return "https://idp/logout"

    def realm_from_issuer(self, issuer):
        return "default"

    def issuer_is_allowed(self, issuer, *, realm):
        return True

    def audience_is_allowed(self, payload):
        return True

    def client_id(self):
        return "client"

    def client_auth_params(self):
        return {}

    def scopes(self):
        return ("openid", "email", "profile", "offline_access")

    def extra_authorize_params(self, realm):
        return {"audience": "https://api.example", "organization": "org_123", "state": "must-not-override"}


def test_oidc_hooks_extend_the_authorization_request_without_overriding_core_params():
    url = _HookedClient().build_authorization_url(realm="default", redirect_uri="https://app/cb", state="s1")
    query = parse_qs(urlparse(url).query)
    assert query["scope"] == ["openid email profile offline_access"]
    assert query["audience"] == ["https://api.example"]
    assert query["organization"] == ["org_123"]
    assert query["state"] == ["s1"]
