"""Regression coverage for architecture review finding I3:
startup/shared_realm_bootstrap.py (mass-UPDATE across every dynamically-
discovered tenant-scoped table, plus tenant-prefixed group-identifier
renames, to reconcile a legacy tenant id with its canonical Keycloak
organization id) had 429 lines of tests deleted in commit 323eb64c0 while
its own implementation only changed 39 lines in the same rewrite. This is
exactly the kind of easy-to-get-wrong logic (mass-UPDATE across dynamic
tables, idempotency, identifier collisions) that most needs a safety net.

Covers: id-canonicalization across multiple tables, group-identifier
collision handling, and the no-op paths (unit_testing skip, table-missing,
and "nothing actually changed").
"""

from __future__ import annotations

import time

import pytest
from flask import g

from m8flow_backend.integrations.auth.base.models import Tenant, TenantRef
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from m8flow_backend.models.native import SecretModel
from m8flow_backend.startup import shared_realm_bootstrap as bootstrap


@pytest.fixture(autouse=True)
def _bind_request_scoped_session(app, db_session):
    """shared_realm_bootstrap reads/writes through db.session
    (m8flow_backend.db.db), which resolves to a *brand new* Session on every
    access outside of a Flask request context (get_session_factory() is a
    plain sessionmaker, not scoped) -- including inside reconcile's own
    `with flask_app.app_context():`, which is not a request context. Pin
    g.db_session to the shared `db_session` fixture so every access inside
    the module under test sees the same session this file seeds and asserts
    against, the way a real request would provide it."""
    with app.test_request_context("/"):
        g.db_session = db_session
        yield


class _FakeDirectoryAdmin:
    def __init__(self, tenant: Tenant):
        self._tenant = tenant

    def get_tenant(self, tenant_ref: TenantRef) -> Tenant:
        assert tenant_ref.alias == self._tenant.ref.alias
        return self._tenant


class _FakeAuthProvider:
    def __init__(self, tenant: Tenant):
        self._tenant = tenant
        self.directory_admin = _FakeDirectoryAdmin(tenant)

    def default_tenant_ref(self) -> TenantRef:
        return TenantRef(alias=self._tenant.ref.alias, name=self._tenant.display_name)


def _seed_tenant(db_session, *, tenant_id: str, slug: str, name: str) -> M8flowTenantModel:
    now = int(time.time())
    tenant = M8flowTenantModel(
        id=tenant_id,
        slug=slug,
        name=name,
        status=TenantStatus.ACTIVE.value,
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


def _seed_group(db_session, identifier: str):
    from m8flow_bpmn_core.models.group import GroupModel

    group = GroupModel(identifier=identifier, name=identifier, source_is_open_id=True)
    db_session.add(group)
    db_session.commit()
    return group


# -- _tenant_scoped_table_names ----------------------------------------------


def test_tenant_scoped_table_names_finds_tables_with_m8f_tenant_id_and_excludes_m8flow_tenant(db_engine):
    table_names = bootstrap._tenant_scoped_table_names(db_engine)

    assert "secret" in table_names
    assert "m8flow_tenant" not in table_names


# -- _update_tenant_scoped_rows -----------------------------------------------


def test_update_tenant_scoped_rows_updates_matching_rows_across_multiple_tables(db_session, db_engine):
    db_session.add(SecretModel(key="k1", value="v1", m8f_tenant_id="old-id", created_at_in_seconds=0, updated_at_in_seconds=0))
    db_session.add(SecretModel(key="k2", value="v2", m8f_tenant_id="old-id", created_at_in_seconds=0, updated_at_in_seconds=0))
    db_session.add(SecretModel(key="k3", value="v3", m8f_tenant_id="other-tenant", created_at_in_seconds=0, updated_at_in_seconds=0))
    db_session.commit()

    updated_tables = bootstrap._update_tenant_scoped_rows(db_session, db_engine, "old-id", "new-id")
    db_session.commit()

    assert "secret" in updated_tables
    remaining_old = db_session.query(SecretModel).filter_by(m8f_tenant_id="old-id").count()
    moved = db_session.query(SecretModel).filter_by(m8f_tenant_id="new-id").count()
    untouched = db_session.query(SecretModel).filter_by(m8f_tenant_id="other-tenant").count()
    assert remaining_old == 0
    assert moved == 2
    assert untouched == 1


def test_update_tenant_scoped_rows_is_a_noop_when_nothing_matches(db_session, db_engine):
    db_session.add(SecretModel(key="k1", value="v1", m8f_tenant_id="other-tenant", created_at_in_seconds=0, updated_at_in_seconds=0))
    db_session.commit()

    updated_tables = bootstrap._update_tenant_scoped_rows(db_session, db_engine, "old-id", "new-id")

    assert updated_tables == []


# -- _rename_tenant_scoped_groups ---------------------------------------------


def test_rename_tenant_scoped_groups_renames_matching_prefixed_groups_only(db_session):
    _seed_group(db_session, "old-id:editor")
    _seed_group(db_session, "old-id:reviewer")
    _seed_group(db_session, "other-tenant:editor")
    _seed_group(db_session, "super-admin")

    renamed = bootstrap._rename_tenant_scoped_groups(db_session, "old-id", "new-id")
    db_session.commit()

    assert sorted(renamed) == [("old-id:editor", "new-id:editor"), ("old-id:reviewer", "new-id:reviewer")]

    from m8flow_bpmn_core.models.group import GroupModel

    identifiers = {row.identifier for row in db_session.query(GroupModel).all()}
    assert identifiers == {"new-id:editor", "new-id:reviewer", "other-tenant:editor", "super-admin"}


def test_rename_tenant_scoped_groups_skips_on_identifier_collision(db_session):
    """If new-id:editor already exists (a different group), the rename must
    not silently collide -- old-id:editor stays as-is rather than raising or
    corrupting the pre-existing new-id:editor row."""
    _seed_group(db_session, "old-id:editor")
    _seed_group(db_session, "new-id:editor")

    renamed = bootstrap._rename_tenant_scoped_groups(db_session, "old-id", "new-id")
    db_session.commit()

    assert renamed == []

    from m8flow_bpmn_core.models.group import GroupModel

    identifiers = {row.identifier for row in db_session.query(GroupModel).all()}
    assert identifiers == {"old-id:editor", "new-id:editor"}


# -- reconcile_default_shared_realm_tenant ------------------------------------


@pytest.fixture
def _real_reconciliation(monkeypatch):
    """reconcile_default_shared_realm_tenant no-ops under unit_testing (see the
    dedicated no-op test below) -- these tests exercise the real body, the way
    it runs at actual startup."""
    monkeypatch.setattr(bootstrap, "is_unit_testing_environment", lambda: False)


def test_reconcile_is_a_noop_under_unit_testing_environment(app, db_session, monkeypatch):
    """The default (and every other test in this file's) posture: the whole
    point of this skip is that a throwaway test DB should never trigger a
    real Keycloak call."""
    calls = []
    monkeypatch.setattr(
        bootstrap,
        "get_auth_provider",
        lambda: calls.append("called") or _FakeAuthProvider(
            Tenant(ref=TenantRef(id="should-not-be-called"), display_name="x")
        ),
    )

    bootstrap.reconcile_default_shared_realm_tenant(app)

    assert calls == []


def test_reconcile_creates_canonical_tenant_when_none_exists(app, db_session, monkeypatch, _real_reconciliation):
    from m8flow_backend.integrations.auth.keycloak.settings import default_organization_alias

    alias = default_organization_alias()
    provider = _FakeAuthProvider(
        Tenant(ref=TenantRef(id="org-abc-123", alias=alias), display_name="Shared Org")
    )
    monkeypatch.setattr(bootstrap, "get_auth_provider", lambda: provider)

    bootstrap.reconcile_default_shared_realm_tenant(app)

    tenant = db_session.get(M8flowTenantModel, "org-abc-123")
    assert tenant is not None
    assert tenant.slug == alias
    assert tenant.name == "Shared Org"


def test_reconcile_canonicalizes_legacy_alias_id_tenant_and_updates_scoped_rows_and_groups(
    app, db_session, monkeypatch, _real_reconciliation
):
    from m8flow_backend.integrations.auth.keycloak.settings import default_organization_alias

    alias = default_organization_alias()
    _seed_tenant(db_session, tenant_id=alias, slug=alias, name="Legacy Name")
    db_session.add(
        SecretModel(key="k1", value="v1", m8f_tenant_id=alias, created_at_in_seconds=0, updated_at_in_seconds=0)
    )
    _seed_group(db_session, f"{alias}:editor")

    provider = _FakeAuthProvider(
        Tenant(ref=TenantRef(id="org-real-123", alias=alias), display_name="Real Org Name")
    )
    monkeypatch.setattr(bootstrap, "get_auth_provider", lambda: provider)

    bootstrap.reconcile_default_shared_realm_tenant(app)

    assert db_session.get(M8flowTenantModel, alias) is None
    canonical = db_session.get(M8flowTenantModel, "org-real-123")
    assert canonical is not None
    assert canonical.slug == alias
    assert canonical.name == "Real Org Name"

    secret = db_session.query(SecretModel).filter_by(key="k1").first()
    assert secret.m8f_tenant_id == "org-real-123"

    from m8flow_bpmn_core.models.group import GroupModel

    identifiers = {row.identifier for row in db_session.query(GroupModel).all()}
    assert "org-real-123:editor" in identifiers
    assert f"{alias}:editor" not in identifiers


def test_reconcile_no_op_when_canonical_tenant_already_matches(app, db_session, monkeypatch, _real_reconciliation):
    from m8flow_backend.integrations.auth.keycloak.settings import default_organization_alias

    alias = default_organization_alias()
    _seed_tenant(db_session, tenant_id="org-real-123", slug=alias, name="Real Org Name")

    provider = _FakeAuthProvider(
        Tenant(ref=TenantRef(id="org-real-123", alias=alias), display_name="Real Org Name")
    )
    monkeypatch.setattr(bootstrap, "get_auth_provider", lambda: provider)

    bootstrap.reconcile_default_shared_realm_tenant(app)

    canonical = db_session.get(M8flowTenantModel, "org-real-123")
    assert canonical is not None
    assert canonical.slug == alias
    assert canonical.name == "Real Org Name"
    assert db_session.query(M8flowTenantModel).count() == 1


def test_reconcile_skips_when_m8flow_tenant_table_missing(app, db_session, monkeypatch, _real_reconciliation):
    calls = []
    monkeypatch.setattr(bootstrap, "_m8flow_tenant_table_exists", lambda engine: False)
    monkeypatch.setattr(
        bootstrap,
        "get_auth_provider",
        lambda: calls.append("called"),
    )

    bootstrap.reconcile_default_shared_realm_tenant(app)

    assert calls == []
