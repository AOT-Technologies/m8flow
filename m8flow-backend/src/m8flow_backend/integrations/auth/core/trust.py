"""Host-owned issuer trust policy, applied to every verified token so no
claim shape (legacy, contract, or a new provider's) can route around it.

``super-admin`` is honoured only from a ``TrustDomain.PLATFORM`` issuer. From
any other issuer it is dropped from the top-level roles and from every
membership's roles and groups, so a shared- or tenant-realm protocol mapper
cannot mint a platform admin.
"""
from __future__ import annotations

from dataclasses import replace

from m8flow_backend.integrations.auth.base.models import TrustDomain, VerifiedClaims
from m8flow_backend.integrations.auth.base.roles import SUPER_ADMIN_ROLE


def _without_super_admin(values: list[str]) -> list[str]:
    return [value for value in values if not (isinstance(value, str) and value.strip() == SUPER_ADMIN_ROLE)]


def enforce_trust_policy(claims: VerifiedClaims, trust_domain: TrustDomain) -> VerifiedClaims:
    if trust_domain is TrustDomain.PLATFORM:
        return claims
    return replace(
        claims,
        roles=_without_super_admin(claims.roles),
        memberships=[
            replace(m, roles=_without_super_admin(m.roles), groups=_without_super_admin(m.groups))
            for m in claims.memberships
        ],
    )
