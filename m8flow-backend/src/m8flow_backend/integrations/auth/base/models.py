"""Neutral, provider-agnostic domain objects for the auth seam.

The backend speaks only in these terms; a provider translates them to and from
its own vocabulary (for Keycloak: organizations, groups, realm roles, ...).

These object shapes are the contract both sides depend on: a provider must be
able to express its data in exactly these terms, and the backend never needs
to know more than this to operate on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IssuerRef:
    """Opaque routing hint for session-establishment calls (build_login_url,
    exchange_code, refresh, build_logout_url, get_user, search_users, ...).

    Only the provider may interpret this value. For Keycloak it is a realm
    name — the shared realm, a tenant's spoke realm, or the master realm.
    Another provider might not need it, or might read a different field.

    Never derived from TenantRef: it is often chosen *before* any tenant is
    known (the shared-realm login entry point is the default case), not
    after tenant resolution. Added by the auth-provider-seam wayfinder map's
    ticket 06 (ahead of ticket 13's full port-surface rename) because ticket
    06's host-code drain needed the type to exist; ticket 13 has since
    applied it to the nine pre-existing session methods on ``AuthProvider``,
    which all take ``issuer: IssuerRef`` now. The capability ABCs in
    ``capabilities.py`` (``SupportsUserAdmin.create_user``/``delete_user``)
    were a deliberate exception -- see ticket 01's locked port-surface
    decision, `Scope of the rename -- port boundary only`.
    """

    value: str


@dataclass(frozen=True)
class TenantRef:
    """A tenant as a token/provider references it — never DB-canonicalized here.

    The backend resolves these raw references to the local canonical tenant row.
    """

    id: str | None = None
    alias: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class Membership:
    """A user's membership in one tenant, with that tenant's neutral roles/groups.

    ``roles`` are neutral role names (see ``base.roles``); ``groups`` are neutral
    group identifiers *before* the backend applies tenant qualification.
    """

    tenant_ref: TenantRef
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VerifiedClaims:
    """The authoritative result of verifying a token.

    Everything request-time authorization needs comes from here — no per-request
    provider call. Only trustworthy because the token was cryptographically
    verified (JWKS) before this object was built.
    """

    subject: str
    issuer: str
    username: str | None = None
    email: str | None = None
    roles: list[str] = field(default_factory=list)
    memberships: list[Membership] = field(default_factory=list)
    # The finalized/active tenant a RealmInfoMapper-style claim names
    # explicitly, distinct from `memberships` (every tenant the user belongs
    # to). Added by the auth-provider-seam wayfinder map's ticket 13, per
    # ticket 01's decision 6.
    active_tenant_ref: TenantRef | None = None
    # Verified JWT payload -- debug-only (auth-provider-seam wayfinder map,
    # ticket 10: "Neutralize the token shape"). Kept for diagnosis (logging,
    # a debug endpoint, `g.decoded_token`'s narrow production reader --
    # `auth/bind.py`'s `is_master_issuer` check, which only reads `.issuer`/
    # this field and is explicitly exempted, see that module's
    # `_request_uses_master_realm_without_tenant_context`), but no
    # *production authorization or tenant-resolution decision* may read it.
    # The typed fields above are the contract; a second provider's payload
    # shape (Auth0's `org_id`, namespaced role claims, ...) must not need
    # any code outside this provider's own claims-mapping to change.
    jwt_claims: dict[str, object] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class TokenSet:
    """Tokens returned by an authorization-code exchange or refresh."""

    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None
    expires_in: int | None = None
    refresh_expires_in: int | None = None


@dataclass(frozen=True)
class User:
    """A neutral directory user."""

    subject: str
    username: str | None = None
    email: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class Tenant:
    """A neutral tenant as the provider knows it (pre DB-canonicalization)."""

    ref: TenantRef
    display_name: str | None = None


@dataclass(frozen=True)
class Role:
    """A neutral role name, optionally scoped to a tenant."""

    name: str
    tenant_ref: TenantRef | None = None


@dataclass(frozen=True)
class Group:
    """A neutral group identifier, optionally scoped to a tenant.

    ``path`` (added by the auth-provider-seam wayfinder map's ticket 08) lets
    mutation methods' existing ``-> Group`` return values serve a caller's
    read-after-write API response directly, instead of the caller discarding
    the return value and re-fetching a raw representation just to read a
    field the thin identifier-only model didn't carry.
    """

    identifier: str
    tenant_ref: TenantRef | None = None
    path: str | None = None
