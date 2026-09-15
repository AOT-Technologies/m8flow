"""Realm/issuer-string helpers derived from a persisted ``UserModel.service``
column -- not from a raw token payload.

Every function that used to parse organization/tenant claims directly out of
a decoded JWT payload (``organization_memberships_from_payload``,
``tenant_id_from_payload``, ``tenant_alias_from_payload``, ...) has been
retired (auth-provider-seam wayfinder map, ticket 10: "Neutralize the token
shape"). ``VerifiedClaims.memberships`` and ``VerifiedClaims.active_tenant_ref``
are the neutral, provider-agnostic replacement -- see ``auth/bind.py``'s
``_claims_match_cookie``/``_jwt_tenant`` and
``services/tenant_management_authorization.py``'s
``_normalized_request_tenant_identifiers``, both of which read those typed
fields instead of importing this module's old functions.

``realm_from_service`` operates on ``UserModel.service`` (a string already
persisted on the local user row, itself derived from ``VerifiedClaims.issuer``
at enrollment time) -- not a live token claim -- so it stays: it's a DB-column
parser used for same-realm tie-breaking/deduplication, not a production
authorization or tenant-resolution decision made from a raw payload.
"""

from __future__ import annotations


def extract_realm_from_issuer(iss: str | None) -> str | None:
    """Extract the Keycloak realm name from an issuer URL."""
    if isinstance(iss, str) and "/realms/" in iss:
        return iss.split("/realms/")[-1].split("/")[0]
    return None


def realm_from_service(service: str | None) -> str:
    """Derive a stable tenant-like value from a service/issuer string."""
    realm = extract_realm_from_issuer(service)
    if realm:
        return realm
    if not service:
        return "unknown"
    normalized = service.rstrip("/")
    return normalized.replace("://", "_").replace("/", "_")[-32:] or "unknown"
