"""Direct unit tests on the active-tenant SELECTION core (resolve.py).

No Flask, no DB, no Keycloak -- `Directory` and `TenantRepo` are in-memory
fakes, per the active-tenant deep-module map (ticket 02's design, ticket 03's
collapse). This is the test surface the multi-org RBAC rules (AGENTS.md) now
run through, instead of only a 1700-line route test.
"""

from __future__ import annotations

from m8flow_backend.integrations.auth.base.models import Membership, TenantRef
from m8flow_backend.auth.resolve import (
    ActiveTenant,
    active_membership_needs_enrichment,
    enrich_active_membership,
    group_identifiers_for_membership,
    membership_for_active_tenant,
    select,
)


class _FakeTenantRepo:
    """In-memory TenantRepo: id/slug -> canonical id, no DB."""

    def __init__(self, rows: dict[str, str] | None = None) -> None:
        # maps any identifier (id or slug) -> the canonical tenant id
        self._by_identifier = dict(rows or {})

    def canonical_tenant_id(self, *identifiers: str | None) -> str | None:
        for identifier in identifiers:
            if isinstance(identifier, str) and identifier.strip() in self._by_identifier:
                return self._by_identifier[identifier.strip()]
        return None

    def current_identifiers(self, tenant_id: str) -> set[str]:
        canonical = self.canonical_tenant_id(tenant_id) or tenant_id
        return {i for i, c in self._by_identifier.items() if c == canonical} | {canonical}

    def slug_for_identifier(self, tenant_identifier: str) -> str | None:
        return self.canonical_tenant_id(tenant_identifier)


class _FakeDirectory:
    """In-memory Directory: username -> memberships, no Keycloak call."""

    def __init__(self, memberships_by_username: dict[str, list[Membership]] | None = None) -> None:
        self._by_username = memberships_by_username or {}
        self.calls: list[str] = []

    def list_memberships(self, *, username: str) -> list[Membership]:
        self.calls.append(username)
        return self._by_username.get(username, [])


class _RaisingDirectory:
    def list_memberships(self, *, username: str) -> list[Membership]:
        raise RuntimeError("directory unavailable")


def _membership(*, id: str | None = None, alias: str | None = None, roles=None, groups=None) -> Membership:
    return Membership(tenant_ref=TenantRef(id=id, alias=alias), roles=list(roles or []), groups=list(groups or []))


# ---------- membership_for_active_tenant ----------


def test_membership_for_active_tenant_matches_by_exact_id():
    repo = _FakeTenantRepo()
    m = _membership(id="org-a")
    assert membership_for_active_tenant([m], "org-a", tenant_repo=repo) is m


def test_membership_for_active_tenant_matches_by_alias():
    repo = _FakeTenantRepo()
    m = _membership(id="uuid-1", alias="org-a")
    assert membership_for_active_tenant([m], "org-a", tenant_repo=repo) is m


def test_membership_for_active_tenant_multi_org_picks_correct_one():
    """The core multi-org case: two memberships, only one matches the active tenant."""
    repo = _FakeTenantRepo()
    org_a = _membership(id="org-a", roles=["editor"])
    org_b = _membership(id="org-b", roles=["reviewer"])
    assert membership_for_active_tenant([org_a, org_b], "org-b", tenant_repo=repo) is org_b
    assert membership_for_active_tenant([org_a, org_b], "org-a", tenant_repo=repo) is org_a


def test_membership_for_active_tenant_matches_via_canonical_id():
    """A membership referencing the tenant's slug matches a cookie holding the canonical id."""
    repo = _FakeTenantRepo({"org-a-slug": "canonical-1", "canonical-1": "canonical-1"})
    m = _membership(alias="org-a-slug")
    assert membership_for_active_tenant([m], "canonical-1", tenant_repo=repo) is m


def test_membership_for_active_tenant_no_match_returns_none():
    repo = _FakeTenantRepo()
    m = _membership(id="org-a")
    assert membership_for_active_tenant([m], "org-b", tenant_repo=repo) is None


def test_membership_for_active_tenant_empty_tenant_id_returns_none():
    repo = _FakeTenantRepo()
    m = _membership(id="org-a")
    assert membership_for_active_tenant([m], "", tenant_repo=repo) is None


# ---------- active_membership_needs_enrichment ----------


def test_needs_enrichment_when_membership_has_no_roles_or_groups():
    thin = _membership(id="org-a")
    assert active_membership_needs_enrichment([thin], thin) is True


def test_no_enrichment_when_membership_already_has_roles():
    warm = _membership(id="org-a", roles=["editor"])
    assert active_membership_needs_enrichment([warm], warm) is False


def test_no_enrichment_when_no_memberships_at_all():
    assert active_membership_needs_enrichment([], None) is False


# ---------- enrich_active_membership ----------


def test_enrich_active_membership_calls_directory_and_returns_match():
    directory = _FakeDirectory({"editor": [_membership(id="org-a", roles=["editor", "reviewer"])]})
    repo = _FakeTenantRepo()
    result = enrich_active_membership(
        username="editor", tenant_id="org-a", membership=None, directory=directory, tenant_repo=repo
    )
    assert result is not None
    assert result.roles == ["editor", "reviewer"]
    assert directory.calls == ["editor"]


def test_enrich_active_membership_falls_back_on_directory_failure():
    """AGENTS.md: directory failure must never crash the request; fall back to the thin membership."""
    thin = _membership(id="org-a")
    result = enrich_active_membership(
        username="editor", tenant_id="org-a", membership=thin, directory=_RaisingDirectory(), tenant_repo=_FakeTenantRepo()
    )
    assert result is thin


def test_enrich_active_membership_skips_directory_without_username():
    thin = _membership(id="org-a")
    directory = _FakeDirectory()
    result = enrich_active_membership(
        username=None, tenant_id="org-a", membership=thin, directory=directory, tenant_repo=_FakeTenantRepo()
    )
    assert result is thin
    assert directory.calls == []


# ---------- group_identifiers_for_membership ----------


def test_group_identifiers_qualifies_valid_tenant_roles():
    m = _membership(id="org-a", roles=["editor"], groups=["reviewer"])
    identifiers = group_identifiers_for_membership(m, roles=frozenset(), canonical_tenant_id="org-a")
    assert set(identifiers) == {"org-a:editor", "org-a:reviewer"}


def test_group_identifiers_adds_super_admin_from_top_level_roles():
    m = _membership(id="org-a", roles=["editor"])
    identifiers = group_identifiers_for_membership(m, roles=frozenset({"super-admin"}), canonical_tenant_id="org-a")
    assert "super-admin" in identifiers
    assert "org-a:editor" in identifiers


def test_group_identifiers_ignores_invalid_role_names():
    m = _membership(id="org-a", roles=["not-a-real-role"])
    identifiers = group_identifiers_for_membership(m, roles=frozenset(), canonical_tenant_id="org-a")
    assert identifiers == []


def test_group_identifiers_empty_without_membership():
    identifiers = group_identifiers_for_membership(None, roles=frozenset(), canonical_tenant_id="org-a")
    assert identifiers == []


# ---------- select() — the full composed operation ----------


def test_select_multi_org_active_tenants_local_groups_present():
    """The multi-org case end to end: two orgs on the token, select() returns
    only the active org's group identifiers -- the AGENTS.md scenario this
    deepening exists to make directly testable."""
    org_a = _membership(id="org-a", roles=["editor"])
    org_b = _membership(id="org-b", roles=["reviewer"])
    result = select(
        memberships=[org_a, org_b],
        roles=frozenset(),
        tenant_id="org-b",
        username="someone",
        directory=_FakeDirectory(),
        tenant_repo=_FakeTenantRepo(),
    )
    assert isinstance(result, ActiveTenant)
    assert result.tenant_id == "org-b"
    assert result.group_identifiers == ["org-b:reviewer"]


def test_select_enriches_thin_token_before_computing_groups():
    """A token that only lists org membership (no roles/groups) must be
    enriched from the directory before groups are computed -- AGENTS.md:
    do not treat a listing-only token as authoritative."""
    thin_org = _membership(id="org-a")  # membership present, but no roles/groups
    directory = _FakeDirectory({"editor": [_membership(id="org-a", roles=["editor"])]})
    result = select(
        memberships=[thin_org],
        roles=frozenset(),
        tenant_id="org-a",
        username="editor",
        directory=directory,
        tenant_repo=_FakeTenantRepo(),
    )
    assert result.group_identifiers == ["org-a:editor"]
    assert directory.calls == ["editor"]


def test_select_does_not_enrich_when_membership_already_warm():
    org_a = _membership(id="org-a", roles=["editor"])
    directory = _FakeDirectory({"editor": [_membership(id="org-a", roles=["reviewer"])]})
    result = select(
        memberships=[org_a],
        roles=frozenset(),
        tenant_id="org-a",
        username="editor",
        directory=directory,
        tenant_repo=_FakeTenantRepo(),
    )
    # already-warm membership is used as-is; directory is never consulted
    assert result.group_identifiers == ["org-a:editor"]
    assert directory.calls == []


def test_select_canonicalizes_tenant_id_by_id():
    repo = _FakeTenantRepo({"org-a": "canonical-a"})
    org_a = _membership(id="org-a", roles=["editor"])
    result = select(
        memberships=[org_a], roles=frozenset(), tenant_id="org-a", username="editor",
        directory=_FakeDirectory(), tenant_repo=repo,
    )
    assert result.tenant_id == "canonical-a"
    assert result.group_identifiers == ["canonical-a:editor"]


def test_select_canonicalizes_tenant_id_by_slug():
    repo = _FakeTenantRepo({"org-a-slug": "canonical-a"})
    org_a = _membership(alias="org-a-slug", roles=["editor"])
    result = select(
        memberships=[org_a], roles=frozenset(), tenant_id="org-a-slug", username="editor",
        directory=_FakeDirectory(), tenant_repo=repo,
    )
    assert result.tenant_id == "canonical-a"


def test_select_no_membership_still_carries_super_admin_role():
    result = select(
        memberships=[], roles=frozenset({"super-admin"}), tenant_id="org-a", username="root",
        directory=_FakeDirectory(), tenant_repo=_FakeTenantRepo(),
    )
    assert result.group_identifiers == ["super-admin"]


def test_select_falls_back_to_raw_tenant_id_when_uncanonicalizable():
    result = select(
        memberships=[], roles=frozenset(), tenant_id="unknown-org", username="nobody",
        directory=_FakeDirectory(), tenant_repo=_FakeTenantRepo(),
    )
    assert result.tenant_id == "unknown-org"
    assert result.group_identifiers == []
