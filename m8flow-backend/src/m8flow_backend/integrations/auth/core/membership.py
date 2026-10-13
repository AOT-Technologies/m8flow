"""Membership authority: the single place that decides whether a token's
membership for the active tenant can be used as-is, or must be enriched from
the provider's directory (AGENTS.md: "a token listing organizations is not
authoritative for RBAC").

Moved verbatim from ``m8flow_backend.auth.resolve`` (authProvider-analysis
redesign) so the rule lives with the auth seam, next to the providers whose
token shapes it depends on. ``auth.resolve`` re-exports every name, and its
``select(...)`` keeps composing them unchanged.

Pure: no Flask, no DB, no HTTP. ``Directory`` and ``TenantRepo`` are injected.
"""
from __future__ import annotations

import logging
from typing import Protocol

from m8flow_backend.integrations.auth.base.models import Membership

logger = logging.getLogger(__name__)


class Directory(Protocol):
    """Membership lookup for a user (the thin-token enrichment source). Must
    *raise* on failure -- ``enrich_active_membership`` owns the fallback."""

    def list_memberships(self, *, username: str) -> list[Membership]: ...


class TenantRepo(Protocol):
    """DB-backed tenant-identifier canonicalization (host-supplied)."""

    def canonical_tenant_id(self, *identifiers: str | None) -> str | None: ...

    def current_identifiers(self, tenant_id: str) -> set[str]: ...

    def slug_for_identifier(self, tenant_identifier: str) -> str | None: ...


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
    *,
    require_lane_groups: bool = False,
) -> bool:
    """True when the active membership needs directory group enrichment.

    By default, retain the original auth behavior: a membership with either
    roles or groups is usable without a directory lookup. Lane assignment is
    the one path that needs the stronger rule because role claims alone do not
    identify BPMN lane groups. Callers on that path opt in with
    ``require_lane_groups=True``.

    A membership whose issuer asserted ``roles_complete`` *and* that carries
    groups whenever lanes are required is authoritative as-is; no provider
    sets ``roles_complete`` today, so this is the existing rule unchanged.
    """
    if not memberships:
        return False
    if membership is None:
        return True
    if require_lane_groups:
        return not membership.groups
    if membership.roles_complete:
        return False
    return not membership.roles and not membership.groups


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
        logger.warning("Directory membership enrichment failed for user %s", username, exc_info=True)
        return membership
    return membership_for_active_tenant(directory_memberships, tenant_id, tenant_repo=tenant_repo) or membership
