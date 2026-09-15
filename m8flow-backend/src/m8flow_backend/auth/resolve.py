"""Pure active-tenant selection core: given claims/memberships and a target
tenant, decide which membership is active, whether it needs directory
enrichment, and which tenant-qualified group identifiers apply.

No Flask, no live DB/HTTP -- ``directory`` and ``tenant_repo`` are injected
per ``ports.py``, so this is the test surface for the multi-org RBAC rules
(AGENTS.md): thin-token enrichment, cookie/claim canonicalization, and group
computation are all exercisable with in-memory fakes, no Keycloak/DB needed.

``select(...)`` is the one operation both login-finalize
(``auth.try_finalize_shared_realm_session``) and the in-session tenant switch
call -- see the active-tenant deep-module map, ticket 02's Answer. This
module does NOT mint or persist anything; callers own token lifecycle and
the group-sync write.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from m8flow_backend.integrations.auth.base.models import Membership
from m8flow_backend.integrations.auth.base.roles import SUPER_ADMIN_ROLE, VALID_TENANT_ROLE_NAMES
from m8flow_backend.auth.identity_helpers import qualify_group_identifier
from m8flow_backend.auth.ports import Directory, TenantRepo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActiveTenant:
    """The result of ``select(...)``: which tenant is active and which
    tenant-qualified group identifiers the user's membership grants there."""

    tenant_id: str
    membership: Membership | None
    group_identifiers: list[str] = field(default_factory=list)


def _ref_tokens(membership: Membership) -> set[str]:
    tokens: set[str] = set()
    for value in (membership.tenant_ref.id, membership.tenant_ref.alias, membership.tenant_ref.name):
        if isinstance(value, str) and value.strip():
            tokens.add(value.strip())
    return tokens


def membership_for_active_tenant(
    memberships: list[Membership],
    tenant_id: str,
    *,
    tenant_repo: TenantRepo,
) -> Membership | None:
    """Match one membership to the active tenant by id, alias, name, or
    canonical row -- exact identifier match wins over a canonical-id match."""
    wanted = {tenant_id.strip()} if tenant_id.strip() else set()
    cookie_canonical = tenant_repo.canonical_tenant_id(tenant_id)
    if cookie_canonical:
        wanted.add(cookie_canonical)
    if not wanted:
        return None

    exact: list[Membership] = []
    canonical_hits: list[Membership] = []
    for membership in memberships:
        tokens = _ref_tokens(membership)
        if tokens & wanted:
            exact.append(membership)
            continue
        member_canonical = tenant_repo.canonical_tenant_id(*tokens, tenant_id)
        if member_canonical and member_canonical in wanted:
            canonical_hits.append(membership)
    if exact:
        return exact[0]
    if canonical_hits:
        return canonical_hits[0]
    return None


def active_membership_needs_enrichment(
    memberships: list[Membership],
    membership: Membership | None,
) -> bool:
    """True when the token is "thin": it names memberships but the active one
    carries no roles/groups, so the directory must be consulted (AGENTS.md:
    do not treat a listing-only token as authoritative for RBAC refresh)."""
    if not memberships:
        return False
    if membership is not None and (membership.roles or membership.groups):
        return False
    return True


def enrich_active_membership(
    *,
    username: str | None,
    tenant_id: str,
    membership: Membership | None,
    directory: Directory,
    tenant_repo: TenantRepo,
) -> Membership | None:
    """Consult the directory for the active org's real groups when the token
    was thin. Falls back to the un-enriched membership on any directory
    failure (best-effort, matches the original request-time behavior)."""
    if not isinstance(username, str) or not username.strip():
        return membership
    try:
        directory_memberships = directory.list_memberships(username=username.strip())
    except Exception:
        logger.warning("Thin-token membership enrichment failed for user %s", username, exc_info=True)
        return membership
    return membership_for_active_tenant(directory_memberships, tenant_id, tenant_repo=tenant_repo) or membership


def group_identifiers_for_membership(
    membership: Membership | None,
    *,
    roles: frozenset[str],
    canonical_tenant_id: str,
) -> list[str]:
    """Compute the tenant-qualified group identifiers a membership grants,
    plus the super-admin identifier when the token's top-level roles carry it."""
    identifiers: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            identifiers.append(cleaned)

    if SUPER_ADMIN_ROLE in roles:
        _add(SUPER_ADMIN_ROLE)

    if membership is not None:
        for name in [*membership.roles, *membership.groups]:
            if not isinstance(name, str) or not name.strip():
                continue
            cleaned = name.strip()
            if cleaned == SUPER_ADMIN_ROLE:
                _add(SUPER_ADMIN_ROLE)
            elif cleaned in VALID_TENANT_ROLE_NAMES:
                _add(qualify_group_identifier(cleaned, tenant_id=canonical_tenant_id))

    return identifiers


def select(
    *,
    memberships: list[Membership],
    roles: frozenset[str],
    tenant_id: str,
    username: str | None,
    directory: Directory,
    tenant_repo: TenantRepo,
) -> ActiveTenant:
    """The one active-tenant decision: match -> enrich if thin -> canonicalize
    -> compute group identifiers. Used by both login-finalize and the
    in-session tenant switch; neither mints a token nor persists anything --
    callers own the token lifecycle and the group-sync write."""
    membership = membership_for_active_tenant(memberships, tenant_id, tenant_repo=tenant_repo)
    if active_membership_needs_enrichment(memberships, membership):
        membership = enrich_active_membership(
            username=username,
            tenant_id=tenant_id,
            membership=membership,
            directory=directory,
            tenant_repo=tenant_repo,
        )

    canonical_tenant_id = (
        tenant_repo.canonical_tenant_id(
            tenant_id,
            None if membership is None else membership.tenant_ref.id,
            None if membership is None else membership.tenant_ref.alias,
        )
        or tenant_id
    )

    group_identifiers = group_identifiers_for_membership(
        membership,
        roles=roles,
        canonical_tenant_id=canonical_tenant_id,
    )

    return ActiveTenant(
        tenant_id=canonical_tenant_id,
        membership=membership,
        group_identifiers=group_identifiers,
    )
