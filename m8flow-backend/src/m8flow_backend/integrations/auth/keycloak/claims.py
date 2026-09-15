"""Translate a verified Keycloak access-token payload into VerifiedClaims."""
from __future__ import annotations

from typing import Any

from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, VerifiedClaims
from m8flow_backend.integrations.auth.base.roles import SUPER_ADMIN_ROLE
from m8flow_backend.integrations.auth.keycloak.role_mapping import tenant_roles_for_organization_group

# Realm-name claim keys the m8flow RealmInfoMapper emits, and the extraction
# logic for them. Deliberately duplicated here (not imported) from
# m8flow_backend.auth.claims's realm_name_from_payload/extract_realm_from_issuer
# -- that module is host code and this runs inside the adapter, which must
# never depend on the host (auth.claims already depends on this module, so a
# reverse import would cycle). Ticket 10 (Neutralize the token shape) is
# expected to consolidate onto this copy and retire the host one.
_AUTHENTICATION_IDENTIFIER_CLAIM = "m8flow_authentication_identifier"
_REALM_NAME_CLAIM = "m8flow_realm_name"
_TENANT_NAME_CLAIM = "m8flow_tenant_name"  # legacy RealmInfoMapper claim


def _string_claim(payload: dict[str, Any], claim: str) -> str | None:
    value = payload.get(claim)
    if isinstance(value, str):
        value = value.strip()
        if value:
            return value
    return None


def realm_name_from_payload(payload: dict[str, Any]) -> str | None:
    """Extract the Keycloak realm name a token claims, trying the explicit
    authentication-identifier/realm-name claims before falling back to the
    legacy ``m8flow_tenant_name`` claim."""
    for claim in (_AUTHENTICATION_IDENTIFIER_CLAIM, _REALM_NAME_CLAIM, "realm_name"):
        value = _string_claim(payload, claim)
        if value:
            return value
    return _string_claim(payload, _TENANT_NAME_CLAIM)


def extract_realm_from_issuer(issuer: str | None) -> str | None:
    """Extract the Keycloak realm name from an issuer URL."""
    if isinstance(issuer, str) and "/realms/" in issuer:
        return issuer.split("/realms/")[-1].split("/")[0]
    return None


def _string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _normalize_group_leaf(value: str) -> str:
    return value.strip().strip("/").split("/")[-1].strip()


def _iter_role_strings(payload: dict[str, Any]) -> list[str]:
    collected: list[str] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        if not isinstance(raw, str):
            return
        leaf = _normalize_group_leaf(raw)
        if not leaf or leaf in seen:
            return
        seen.add(leaf)
        collected.append(leaf)

    roles = payload.get("roles")
    if isinstance(roles, list):
        for item in roles:
            _add(item)

    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict):
        realm_roles = realm_access.get("roles")
        if isinstance(realm_roles, list):
            for item in realm_roles:
                _add(item)

    groups = payload.get("groups")
    if isinstance(groups, list):
        for item in groups:
            if isinstance(item, str):
                _add(item)

    return collected


def memberships_from_organization_claim(payload: dict[str, Any]) -> list[Membership]:
    claim = payload.get("organization")
    entries: list[tuple[str | None, dict[str, Any]]] = []
    if isinstance(claim, dict):
        for alias, details in claim.items():
            if isinstance(alias, str) and isinstance(details, dict):
                entries.append((alias.strip() or None, details))
            elif isinstance(alias, str) and alias.strip():
                entries.append((alias.strip(), {}))
    elif isinstance(claim, list):
        for item in claim:
            if isinstance(item, str) and item.strip():
                entries.append((item.strip(), {}))
            elif isinstance(item, dict):
                alias = item.get("alias")
                alias_text = alias.strip() if isinstance(alias, str) else None
                entries.append((alias_text, item))

    memberships: list[Membership] = []
    for alias, details in entries:
        org_id = details.get("id")
        org_name = details.get("name")
        groups_claim = details.get("groups")
        roles: list[str] = []
        if isinstance(groups_claim, list):
            for group in groups_claim:
                if not isinstance(group, str):
                    continue
                leaf = _normalize_group_leaf(group)
                if not leaf:
                    continue
                roles.extend(tenant_roles_for_organization_group(leaf))
        # Neutral identifiers only — never Keycloak leaves like Administrators.
        unique_roles = list(dict.fromkeys(roles))
        memberships.append(
            Membership(
                tenant_ref=TenantRef(
                    id=org_id.strip() if isinstance(org_id, str) and org_id.strip() else None,
                    alias=alias,
                    name=org_name.strip() if isinstance(org_name, str) and org_name.strip() else None,
                ),
                roles=unique_roles,
                groups=list(unique_roles),
            )
        )
    return memberships


def _active_tenant_ref_from_payload(payload: dict[str, Any], memberships: list[Membership]) -> TenantRef | None:
    """The RealmInfoMapper's explicit finalized-tenant signal (ticket 01's
    decision 6): `m8flow_tenant_id`/`m8flow_tenant_alias`, falling back to the
    sole membership when there's exactly one -- mirrors
    active_organization_from_payload's existing single-org shortcut on the
    host side (auth/claims.py), so a single-tenant user needs no explicit
    claim at all."""
    tenant_id = _string(payload.get("m8flow_tenant_id"))
    tenant_alias = _string(payload.get("m8flow_tenant_alias"))
    if tenant_id or tenant_alias:
        return TenantRef(id=tenant_id, alias=tenant_alias)
    if len(memberships) == 1:
        return memberships[0].tenant_ref
    return None


def verified_claims_from_payload(payload: dict[str, Any]) -> VerifiedClaims:
    subject = _string(payload.get("sub"))
    issuer = _string(payload.get("iss"))
    if not subject or not issuer:
        raise ValueError("Verified payload is missing sub or iss")

    raw_roles = _iter_role_strings(payload)
    flattened: list[str] = []
    seen: set[str] = set()
    for name in raw_roles:
        translated = tenant_roles_for_organization_group(name)
        pieces = translated if translated else (name,)
        for piece in pieces:
            if piece == "super-admin":
                piece = SUPER_ADMIN_ROLE
            if piece not in seen:
                seen.add(piece)
                flattened.append(piece)

    memberships = memberships_from_organization_claim(payload)
    for membership in memberships:
        for role in membership.roles:
            if role not in seen:
                seen.add(role)
                flattened.append(role)

    return VerifiedClaims(
        subject=subject,
        issuer=issuer,
        username=_string(payload.get("preferred_username")) or _string(payload.get("username")),
        email=_string(payload.get("email")),
        roles=flattened,
        memberships=memberships,
        active_tenant_ref=_active_tenant_ref_from_payload(payload, memberships),
        jwt_claims=dict(payload),
    )
