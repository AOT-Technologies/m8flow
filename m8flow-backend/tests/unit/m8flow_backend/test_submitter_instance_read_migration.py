"""Regression tests for revoking submitter tenant-wide instance read (M8F-534)."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "b9d2e3f4a5c6_revoke_submitter_tenant_wide_instance_read.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("submitter_instance_read_migration", _MIGRATION_PATH)
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
        sa.table("group", sa.column("id"), sa.column("identifier")).insert(),
        [
            {"id": 1, "identifier": "tenant-a:submitter"},
            {"id": 2, "identifier": "tenant-a:editor"},
            {"id": 3, "identifier": "custom:submitter"},
            {"id": 4, "identifier": "submitter"},
        ],
    )
    connection.execute(sa.table("m8flow_tenant", sa.column("id")).insert(), [{"id": "tenant-a"}])
    connection.execute(
        sa.table("principal", sa.column("id"), sa.column("group_id")).insert(),
        [{"id": 11, "group_id": 1}, {"id": 22, "group_id": 2}, {"id": 33, "group_id": 3}, {"id": 44, "group_id": 4}],
    )
    connection.execute(
        sa.table(
            "permission_target",
            sa.column("id"),
            sa.column("command"),
            sa.column("resource_type"),
            sa.column("resource_id"),
        ).insert(),
        [
            {"id": 101, "command": "process_instance.list", "resource_type": "tenant", "resource_id": "/process-instances"},
            {"id": 102, "command": "process_instance.read", "resource_type": "tenant", "resource_id": "/process-instances/%"},
            {"id": 103, "command": None, "resource_type": "tenant", "resource_id": "/process-instances/for-me"},
            {"id": 104, "command": None, "resource_type": "tenant", "resource_id": "/process-instances%"},
        ],
    )
    connection.execute(
        sa.table(
            "permission_assignment",
            sa.column("id"),
            sa.column("principal_id"),
            sa.column("permission_target_id"),
            sa.column("grant_type"),
            sa.column("permission"),
        ).insert(),
        [
            # Tenant submitter: both tenant-wide reads go; own-instance read and
            # the create grant (process start) stay.
            {"id": 1, "principal_id": 11, "permission_target_id": 101, "grant_type": "permit", "permission": "read"},
            {"id": 2, "principal_id": 11, "permission_target_id": 102, "grant_type": "permit", "permission": "read"},
            {"id": 3, "principal_id": 11, "permission_target_id": 103, "grant_type": "permit", "permission": "read"},
            {"id": 4, "principal_id": 11, "permission_target_id": 104, "grant_type": "permit", "permission": "create"},
            # Editor keeps tenant-wide read.
            {"id": 5, "principal_id": 22, "permission_target_id": 101, "grant_type": "permit", "permission": "read"},
            # Namespaced non-tenant group is untouched; legacy global group is revoked.
            {"id": 6, "principal_id": 33, "permission_target_id": 102, "grant_type": "permit", "permission": "read"},
            {"id": 7, "principal_id": 44, "permission_target_id": 102, "grant_type": "permit", "permission": "read"},
        ],
    )


def _assignments(connection):
    return connection.execute(
        sa.text(
            "SELECT principal_id, permission_target_id, permission FROM permission_assignment "
            "ORDER BY principal_id, permission_target_id, permission"
        )
    ).all()


def test_upgrade_removes_only_submitter_tenant_wide_instance_reads_and_is_idempotent():
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        _seed(connection)
        migration = _migration_module()
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()

        remaining = connection.execute(sa.text("SELECT id FROM permission_assignment ORDER BY id")).scalars().all()

    assert remaining == [3, 4, 5, 6]


def test_downgrade_restores_submitter_tenant_wide_reads_once():
    """Rolled-back code needs the grants back: its seed marker check never re-imports."""
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        _seed(connection)
        before = _assignments(connection)
        migration = _migration_module()
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.downgrade()
            migration.downgrade()
        after = _assignments(connection)
        restored = connection.execute(
            sa.text(
                "SELECT grant_type FROM permission_assignment "
                "WHERE principal_id IN (11, 44) AND permission_target_id IN (101, 102)"
            )
        ).scalars().all()

    # The tenant and legacy global submitter groups get both reads back, once each
    # (the legacy group gains /process-instances, which the old YAML granted too);
    # every other grant is as before.
    assert after == sorted(set(before) | {(44, 101, "read")})
    assert restored == ["permit"] * 4


def test_downgrade_keeps_existing_denies_and_restores_only_missing_reads():
    """A deny/read row holds the (principal, target, read) slot -- the table is unique
    on it -- so downgrade leaves it alone instead of colliding with it; every other
    missing submitter read is restored, and reads already present are not duplicated."""
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        _seed(connection)
        connection.execute(sa.text("DELETE FROM permission_assignment WHERE principal_id IN (11, 44)"))
        connection.execute(
            sa.text(
                "INSERT INTO permission_assignment (principal_id, permission_target_id, grant_type, permission) "
                "VALUES (11, 101, 'deny', 'read'), (44, 102, 'permit', 'read')"
            )
        )
        migration = _migration_module()
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        rows = connection.execute(
            sa.text(
                "SELECT principal_id, permission_target_id, grant_type FROM permission_assignment "
                "WHERE principal_id IN (11, 44) AND permission = 'read' AND permission_target_id IN (101, 102) "
                "ORDER BY principal_id, permission_target_id"
            )
        ).all()

    assert rows == [(11, 101, "deny"), (11, 102, "permit"), (44, 101, "permit"), (44, 102, "permit")]


def test_upgrade_fails_loudly_when_required_authorization_tables_are_missing(caplog):
    engine = sa.create_engine("sqlite://")
    migration = _migration_module()

    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            with caplog.at_level(logging.ERROR, logger="alembic.runtime.migration"):
                with pytest.raises(RuntimeError, match="required authorization tables are missing"):
                    migration.upgrade()

    assert "permission_assignment" in caplog.text
