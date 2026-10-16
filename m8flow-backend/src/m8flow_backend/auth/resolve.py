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

# The membership-authority rule (match / needs-enrichment / enrich) moved to
# the auth seam (authProvider-analysis redesign); re-exported unchanged so
# every existing import of these names keeps working.
from m8flow_backend.integrations.auth.core.membership import (  # noqa: F401 -- re-exported
    _ref_tokens,
    active_membership_needs_enrichment,
    enrich_active_membership,
    membership_for_active_tenant,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActiveTenant:
    """The result of ``select(...)``: which tenant is active and which
    tenant-qualified group identifiers the user's membership grants there."""

    tenant_id: str
    membership: Membership | None
    group_identifiers: list[str] = field(default_factory=list)
    lane_group_identifiers: list[str] = field(default_factory=list)


def group_identifiers_for_membership(
    membership: Membership | None,
    *,
    roles: frozenset[str],
    canonical_tenant_id: str,
) -> list[str]:
    """Compute the tenant-qualified group identifiers a membership grants,
    plus the super-admin identifier when the token's top-level roles carry it.
    A membership never grants super-admin."""
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
            if cleaned in VALID_TENANT_ROLE_NAMES:
                _add(qualify_group_identifier(cleaned, tenant_id=canonical_tenant_id))

    return identifiers


def lane_group_identifiers_for_membership(membership: Membership | None) -> list[str]:
    """Return normalized directory groups that can back workflow lanes.

    Keycloak's default organization groups also map to RBAC roles, but a BPMN
    lane uses the directory-group name (for example ``Submitters``). Keep
    those names separate from RBAC identifiers so they can create the core's
    deterministic lane-group assignment without becoming permission grants.
    """
    if membership is None:
        return []
    identifiers: list[str] = []
    seen: set[str] = set()

    def _add(value: object) -> None:
        if not isinstance(value, str):
            return
        cleaned = value.strip().strip("/").split("/")[-1].strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            identifiers.append(cleaned)

    for group_name in membership.groups:
        _add(group_name)
    return identifiers


def select(
    *,
    memberships: list[Membership],
    roles: frozenset[str],
    tenant_id: str,
    username: str | None,
    directory: Directory,
    tenant_repo: TenantRepo,
    require_lane_groups: bool = False,
) -> ActiveTenant:
    """The one active-tenant decision: match -> enrich if thin -> canonicalize
    -> compute group identifiers. Used by both login-finalize and the
    in-session tenant switch; neither mints a token nor persists anything --
    callers own the token lifecycle and the group-sync write."""
    membership = membership_for_active_tenant(memberships, tenant_id, tenant_repo=tenant_repo)
    if active_membership_needs_enrichment(
        memberships,
        membership,
        require_lane_groups=require_lane_groups,
    ):
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
    lane_group_identifiers = lane_group_identifiers_for_membership(membership)

    return ActiveTenant(
        tenant_id=canonical_tenant_id,
        membership=membership,
        group_identifiers=group_identifiers,
        lane_group_identifiers=lane_group_identifiers,
    )
