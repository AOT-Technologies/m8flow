"""Regression tests for revoking editor/viewer tenant-wide instance read (M8F-627)."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.dialects import postgresql


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "c1e4f5a6b7d8_revoke_editor_viewer_tenant_wide_instance_read.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("editor_viewer_instance_read_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema(engine):
    metadata = sa.MetaData()
    sa.Table("group", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("identifier", sa.String))
    sa.Table("principal", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("group_id", sa.Integer))
    sa.Table(
        "permission_target",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("command", sa.String),
        sa.Column("resource_type", sa.String),
        sa.Column("resource_id", sa.String),
    )
    sa.Table(
        "permission_assignment",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("principal_id", sa.Integer),
        sa.Column("permission_target_id", sa.Integer),
        sa.Column("grant_type", sa.String),
        sa.Column("permission", sa.String),
        # Mirrors m8f_permission_assignment_principal_target_permission_key.
        sa.UniqueConstraint("principal_id", "permission_target_id", "permission"),
    )
    sa.Table("m8flow_tenant", metadata, sa.Column("id", sa.String, primary_key=True))
    metadata.create_all(engine)


def _seed(connection):
    connection.execute(
        sa.text(
            'INSERT INTO "group" (id, identifier) VALUES '
            "(1, 'tenant-a:editor'), (2, 'tenant-a:viewer'), (3, 'tenant-a:tenant-admin'), "
            "(4, 'custom:editor'), (5, 'viewer')"
        )
    )
    connection.execute(sa.text("INSERT INTO m8flow_tenant (id) VALUES ('tenant-a')"))
    connection.execute(
        sa.text("INSERT INTO principal (id, group_id) VALUES (11, 1), (22, 2), (33, 3), (44, 4), (55, 5)")
    )
    connection.execute(
        sa.text(
            "INSERT INTO permission_target (id, command, resource_type, resource_id) VALUES "
            "(101, 'process_instance.list', 'tenant', '/process-instances'), "
            "(102, 'process_instance.read', 'tenant', '/process-instances/%'), "
            "(103, NULL, 'tenant', '/process-instances/for-me')"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO permission_assignment (id, principal_id, permission_target_id, grant_type, permission) "
            "VALUES "
            # Tenant editor: both tenant-wide reads go; lifecycle execute and own read stay.
            "(1, 11, 101, 'permit', 'read'), (2, 11, 102, 'permit', 'read'), "
            "(3, 11, 102, 'permit', 'execute'), (4, 11, 103, 'permit', 'read'), "
            # Tenant viewer: both tenant-wide reads go.
            "(5, 22, 101, 'permit', 'read'), (6, 22, 102, 'permit', 'read'), "
            # Tenant-admin keeps tenant-wide read.
            "(7, 33, 101, 'permit', 'read'), "
            # Namespaced non-tenant group is untouched; legacy global viewer is revoked.
            "(8, 44, 101, 'permit', 'read'), (9, 55, 101, 'permit', 'read')"
        )
    )


def _ids(connection):
    return connection.execute(sa.text("SELECT id FROM permission_assignment ORDER BY id")).scalars().all()


def _run(connection, *steps):
    migration = _migration_module()
    with Operations.context(MigrationContext.configure(connection)):
        for step in steps:
            getattr(migration, step)()


def test_upgrade_removes_only_editor_and_viewer_tenant_wide_reads_and_is_idempotent():
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        _seed(connection)
        _run(connection, "upgrade", "upgrade")
        assert _ids(connection) == [3, 4, 7, 8]


def test_downgrade_restores_editor_and_viewer_tenant_wide_reads_once():
    """Rolled-back code needs the grants back: its seed marker check never re-imports."""
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        _seed(connection)
        _run(connection, "upgrade", "downgrade", "downgrade")
        restored = connection.execute(
            sa.text(
                "SELECT principal_id, permission_target_id FROM permission_assignment "
                "WHERE permission = 'read' AND permission_target_id IN (101, 102) ORDER BY 1, 2"
            )
        ).all()

    # Tenant editor and viewer get both back. The legacy global viewer (55) stays revoked:
    # the old seed never granted global groups, so downgrade never broadens them.
    assert restored == [(11, 101), (11, 102), (22, 101), (22, 102), (33, 101), (44, 101)]


def test_downgrade_never_adds_grants_to_a_legacy_global_group():
    """A global viewer that held only /process-instances read (or nothing) must not
    gain /process-instances/% read on rollback."""
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        _seed(connection)
        _run(connection, "downgrade")
        global_viewer = connection.execute(
            sa.text("SELECT permission_target_id FROM permission_assignment WHERE principal_id = 55")
        ).scalars().all()

    assert global_viewer == [101]


def test_upgrade_revokes_tenant_wide_reads_whatever_their_command():
    """Route authorization ignores the target command, so a read on these resource IDs
    under another (or no) command still grants tenant-wide read and must go. Non-read
    permissions on the same targets, such as starting an instance, are kept."""
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        _seed(connection)
        connection.execute(
            sa.text(
                "INSERT INTO permission_target (id, command, resource_type, resource_id) VALUES "
                "(104, 'legacy.other', 'tenant', '/process-instances'), "
                "(105, NULL, 'tenant', '/process-instances/%'), "
                "(106, 'process.start', 'tenant', '/process-instances')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO permission_assignment (id, principal_id, permission_target_id, grant_type, permission) "
                "VALUES (20, 11, 104, 'permit', 'read'), (21, 22, 105, 'permit', 'all'), "
                "(22, 11, 106, 'permit', 'create')"
            )
        )
        _run(connection, "upgrade")
        remaining = set(_ids(connection))

    assert {20, 21}.isdisjoint(remaining)
    assert 22 in remaining


def test_downgrade_keeps_existing_denies_and_restores_only_missing_reads():
    """A deny row holds the (principal, target, read) slot -- the table is unique on
    it -- so downgrade leaves it alone instead of colliding with it."""
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        _seed(connection)
        connection.execute(sa.text("DELETE FROM permission_assignment WHERE principal_id = 22"))
        connection.execute(
            sa.text(
                "INSERT INTO permission_assignment (principal_id, permission_target_id, grant_type, permission) "
                "VALUES (22, 101, 'deny', 'read')"
            )
        )
        _run(connection, "downgrade")
        rows = connection.execute(
            sa.text(
                "SELECT permission_target_id, grant_type FROM permission_assignment "
                "WHERE principal_id = 22 AND permission = 'read' ORDER BY 1"
            )
        ).all()

    assert rows == [(101, "deny"), (102, "permit")]


def test_role_query_compiles_to_in_subqueries_for_postgresql():
    """Tenant-qualified identifiers are IN (SELECT ...) on the production dialect,
    with the reserved-word group table quoted."""
    engine = sa.create_engine("sqlite://")
    _schema(engine)

    with engine.connect() as connection:
        sql = str(_migration_module()._role_principals_query(connection).compile(dialect=postgresql.dialect()))

    assert 'JOIN "group"' in sql
    assert '"group".identifier IN (SELECT CAST(m8flow_tenant.id AS VARCHAR) ||' in sql


def test_upgrade_fails_loudly_when_required_authorization_tables_are_missing(caplog):
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        with caplog.at_level(logging.ERROR, logger="alembic.runtime.migration"):
            with pytest.raises(RuntimeError, match="required authorization tables are missing"):
                _run(connection, "upgrade")

    assert "permission_assignment" in caplog.text
