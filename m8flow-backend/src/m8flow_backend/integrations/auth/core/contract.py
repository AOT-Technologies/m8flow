"""The m8flow claims contract v1: one versioned claim an identity provider can
emit at token-mint time so m8flow needs no vendor-specific claim parsing
(authProvider-analysis combined design, section 3.8).

Shape: ``m8flow-claims.v1.schema.json`` next to this module. The same schema
and golden fixtures are meant to be asserted by the IdP-side emitters (the
Keycloak protocol mapper, an Auth0 post-login Action).

Trust rules (host-owned, identical for every IdP):

- The claim is only read from a token whose signature and issuer the provider
  already verified.
- ``domain`` is a hint; the provider's issuer configuration decides the trust
  domain, and a mismatch is rejected.
- ``platform_roles`` are honoured only for ``TrustDomain.PLATFORM`` issuers.
- A ``TrustDomain.TENANT`` issuer speaks only for its own tenant: the tenant's
  ``alias`` must equal the issuer key (the Keycloak realm name), and only
  that alias is kept so an asserted ``id`` or ``name`` cannot match another
  tenant.

Opt-in: providers consult the contract only when
``M8FLOW_AUTH_CONTRACT_CLAIMS`` is truthy, so existing tokens and behaviour are
unchanged by default.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, TrustDomain

CONTRACT_CLAIMS_ENV = "M8FLOW_AUTH_CONTRACT_CLAIMS"
CONTRACT_CLAIM_KEY_ENV = "M8FLOW_AUTH_CONTRACT_CLAIM_KEY"
DEFAULT_CONTRACT_CLAIM_KEY = "https://m8flow.io/claims"
SUPPORTED_CONTRACT_VERSIONS = frozenset({1})
_SCHEMA_PATH = Path(__file__).with_name("m8flow-claims.v1.schema.json")
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def contract_claims_enabled() -> bool:
    return (os.environ.get(CONTRACT_CLAIMS_ENV) or "").strip().lower() in _TRUTHY


def contract_claim_key() -> str:
    return (os.environ.get(CONTRACT_CLAIM_KEY_ENV) or "").strip() or DEFAULT_CONTRACT_CLAIM_KEY


@lru_cache(maxsize=1)
def contract_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text())


@dataclass(frozen=True)
class ContractClaims:
    """Neutral facts a contract claim asserts, after validation and trust policy."""

    memberships: list[Membership] = field(default_factory=list)
    memberships_complete: bool = False
    active_tenant_ref: TenantRef | None = None
    platform_roles: frozenset[str] = frozenset()


def _tenant_ref(raw: Mapping[str, Any]) -> TenantRef:
    def _clean(value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    return TenantRef(id=_clean(raw.get("id")), alias=_clean(raw.get("alias")), name=_clean(raw.get("name")))


def _bind_to_issuer(ref: TenantRef, issuer_key: str | None) -> TenantRef:
    if not issuer_key or ref.alias != issuer_key:
        raise ValueError("A tenant-domain issuer may only assert its own tenant")
    return TenantRef(alias=issuer_key)


def parse_contract_claim(
    payload: Mapping[str, Any],
    *,
    trust_domain: TrustDomain,
    issuer_key: str | None = None,
    claim_key: str | None = None,
) -> ContractClaims | None:
    """Return the contract facts in ``payload``, or ``None`` when the claim is
    absent. Raises ``ValueError`` (mapped to ``TokenInvalid`` by the provider)
    when the claim is present but malformed, from an unsupported version, or
    disagrees with the issuer's configured trust domain -- fail closed."""
    key = claim_key or contract_claim_key()
    raw = payload.get(key)
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("m8flow contract claim must be an object")
    version = raw.get("v")
    if version not in SUPPORTED_CONTRACT_VERSIONS:
        raise ValueError(f"Unsupported m8flow contract claim version {version!r}")
    try:
        jsonschema.validate(instance=dict(raw), schema=contract_schema())
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Invalid m8flow contract claim: {exc.message}") from exc

    hinted = raw.get("domain")
    if hinted is not None and TrustDomain(hinted) is not trust_domain:
        raise ValueError(
            f"m8flow contract claim domain {hinted!r} does not match the issuer's trust domain {trust_domain.value!r}"
        )

    memberships = [
        Membership(
            tenant_ref=_tenant_ref(grant["tenant"]),
            roles=list(grant.get("roles") or []),
            groups=list(grant.get("groups") or []),
            roles_complete=bool(grant.get("roles_complete", False)),
        )
        for grant in raw.get("tenants") or []
    ]
    active_raw = raw.get("active_tenant")
    active = _tenant_ref(active_raw) if isinstance(active_raw, Mapping) else None
    platform_roles = frozenset(raw.get("platform_roles") or ()) if trust_domain is TrustDomain.PLATFORM else frozenset()

    if trust_domain is TrustDomain.TENANT:
        # A tenant issuer can only ever speak for its own single tenant.
        if len(memberships) > 1:
            raise ValueError("A tenant-domain issuer may assert at most one tenant")
        memberships = [replace(m, tenant_ref=_bind_to_issuer(m.tenant_ref, issuer_key)) for m in memberships]
        if active is not None:
            active = _bind_to_issuer(active, issuer_key)
        elif memberships:
            active = memberships[0].tenant_ref

    return ContractClaims(
        memberships=memberships,
        memberships_complete=bool(raw.get("tenants_complete", False)),
        active_tenant_ref=active,
        platform_roles=platform_roles,
    )
