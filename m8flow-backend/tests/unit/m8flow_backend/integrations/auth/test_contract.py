"""The m8flow claims contract v1 (``integrations.auth.core.contract``).

The golden fixtures under ``tests/fixtures/auth/contract/`` are the
cross-language contract: IdP-side emitters (the Keycloak protocol mapper, an
Auth0 post-login Action) should be tested against the same files.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, TrustDomain
from m8flow_backend.integrations.auth.core.contract import (
    CONTRACT_CLAIM_KEY_ENV,
    CONTRACT_CLAIMS_ENV,
    DEFAULT_CONTRACT_CLAIM_KEY,
    contract_claim_key,
    contract_claims_enabled,
    contract_schema,
    parse_contract_claim,
)

_FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "auth" / "contract"


def _fixtures() -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted(_FIXTURES.glob("*.json"))]


def _payload(claim) -> dict:
    return {DEFAULT_CONTRACT_CLAIM_KEY: claim}


def test_schema_is_itself_valid():
    jsonschema.Draft202012Validator.check_schema(contract_schema())


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda fixture: fixture["name"])
def test_golden_contract_fixtures(fixture):
    domain = TrustDomain(fixture["trust_domain"])
    issuer_key = fixture.get("issuer_key")
    if "error" in fixture:
        with pytest.raises(ValueError, match=fixture["error"]):
            parse_contract_claim(_payload(fixture["claim"]), trust_domain=domain, issuer_key=issuer_key)
        return
    jsonschema.validate(fixture["claim"], contract_schema())
    parsed = parse_contract_claim(_payload(fixture["claim"]), trust_domain=domain, issuer_key=issuer_key)
    expected = fixture["expected"]
    assert [
        {
            "tenant": {"id": m.tenant_ref.id, "alias": m.tenant_ref.alias, "name": m.tenant_ref.name},
            "roles": m.roles,
            "groups": m.groups,
            "roles_complete": m.roles_complete,
        }
        for m in parsed.memberships
    ] == expected["memberships"]
    assert parsed.memberships_complete is expected["memberships_complete"]
    active = parsed.active_tenant_ref
    assert (None if active is None else {"id": active.id, "alias": active.alias, "name": active.name}) == expected[
        "active_tenant"
    ]
    assert sorted(parsed.platform_roles) == expected["platform_roles"]


def test_absent_claim_returns_none():
    assert parse_contract_claim({"sub": "s"}, trust_domain=TrustDomain.SHARED) is None


@pytest.mark.parametrize(
    ("claim", "message"),
    [
        ("not-an-object", "must be an object"),
        ({"v": 2}, "Unsupported"),
        ({}, "Unsupported"),
        ({"v": 1, "tenants": [{"tenant": {"id": "t"}, "roles": ["root"]}]}, "Invalid"),
        ({"v": 1, "platform_roles": ["tenant-admin"]}, "Invalid"),
        ({"v": 1, "tenants": [{"tenant": {}}]}, "Invalid"),
    ],
)
def test_malformed_claims_fail_closed(claim, message):
    with pytest.raises(ValueError, match=message):
        parse_contract_claim(_payload(claim), trust_domain=TrustDomain.SHARED)


def test_tenant_issuer_may_only_assert_one_tenant():
    claim = {"v": 1, "tenants": [{"tenant": {"id": "a"}}, {"tenant": {"id": "b"}}]}
    with pytest.raises(ValueError, match="at most one tenant"):
        parse_contract_claim(_payload(claim), trust_domain=TrustDomain.TENANT)


def test_tenant_issuer_defaults_active_tenant_to_its_tenant():
    claim = {"v": 1, "tenants": [{"tenant": {"alias": "acme"}, "roles": ["editor"], "roles_complete": True}]}
    parsed = parse_contract_claim(_payload(claim), trust_domain=TrustDomain.TENANT, issuer_key="acme")
    assert parsed.active_tenant_ref == TenantRef(alias="acme")
    assert parsed.memberships == [Membership(tenant_ref=TenantRef(alias="acme"), roles=["editor"], roles_complete=True)]


@pytest.mark.parametrize(
    ("tenant", "issuer_key"),
    [
        ({"id": "acme"}, "acme"),  # no alias: the tenant cannot be tied to the issuer
        ({"alias": "acme"}, None),  # issuer key unknown
    ],
)
def test_tenant_issuer_may_only_assert_its_own_tenant(tenant, issuer_key):
    claim = {"v": 1, "tenants": [{"tenant": tenant, "roles": ["tenant-admin"]}]}
    with pytest.raises(ValueError, match="only assert its own tenant"):
        parse_contract_claim(_payload(claim), trust_domain=TrustDomain.TENANT, issuer_key=issuer_key)


def test_tenant_issuer_active_tenant_must_be_its_own():
    claim = {"v": 1, "active_tenant": {"alias": "globex"}, "tenants": [{"tenant": {"alias": "acme"}}]}
    with pytest.raises(ValueError, match="only assert its own tenant"):
        parse_contract_claim(_payload(claim), trust_domain=TrustDomain.TENANT, issuer_key="acme")


def test_tenant_issuer_cannot_reach_another_tenant_through_id_or_name():
    claim = {"v": 1, "tenants": [{"tenant": {"id": "globex-id", "alias": "acme", "name": "globex"}}]}
    parsed = parse_contract_claim(_payload(claim), trust_domain=TrustDomain.TENANT, issuer_key="acme")
    assert parsed.memberships[0].tenant_ref == TenantRef(alias="acme")
    assert parsed.active_tenant_ref == TenantRef(alias="acme")


def test_flag_and_key_env(monkeypatch):
    monkeypatch.delenv(CONTRACT_CLAIMS_ENV, raising=False)
    monkeypatch.delenv(CONTRACT_CLAIM_KEY_ENV, raising=False)
    assert contract_claims_enabled() is False
    assert contract_claim_key() == DEFAULT_CONTRACT_CLAIM_KEY
    monkeypatch.setenv(CONTRACT_CLAIMS_ENV, "yes")
    monkeypatch.setenv(CONTRACT_CLAIM_KEY_ENV, "m8flow")
    assert contract_claims_enabled() is True
    assert contract_claim_key() == "m8flow"
    assert parse_contract_claim({"m8flow": {"v": 1}}, trust_domain=TrustDomain.SHARED) is not None
