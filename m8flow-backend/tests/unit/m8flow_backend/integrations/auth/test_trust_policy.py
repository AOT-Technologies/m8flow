"""Host-owned issuer trust policy (``integrations.auth.core.trust``)."""
from __future__ import annotations

import pytest

from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, TrustDomain, VerifiedClaims
from m8flow_backend.integrations.auth.core.trust import enforce_trust_policy


def _claims() -> VerifiedClaims:
    return VerifiedClaims(
        subject="s",
        issuer="https://idp.example/realms/m8flow",
        roles=["editor", "super-admin"],
        memberships=[
            Membership(tenant_ref=TenantRef(id="t1"), roles=["super-admin", "viewer"], groups=["super-admin", "Designers"])
        ],
    )


@pytest.mark.parametrize("domain", [TrustDomain.SHARED, TrustDomain.TENANT])
def test_super_admin_is_stripped_from_non_platform_issuers(domain):
    claims = enforce_trust_policy(_claims(), domain)
    assert claims.roles == ["editor"]
    assert claims.memberships == [Membership(tenant_ref=TenantRef(id="t1"), roles=["viewer"], groups=["Designers"])]


def test_platform_issuer_keeps_super_admin():
    assert enforce_trust_policy(_claims(), TrustDomain.PLATFORM) == _claims()
