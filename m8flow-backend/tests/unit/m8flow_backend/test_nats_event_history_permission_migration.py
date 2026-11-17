"""Revoking tenant-admin NATS event-history grants (M8F-700)."""

from __future__ import annotations

import importlib.util
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
    / "c7e9a1b3d5f7_revoke_tenant_admin_nats_event_history.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("nats_event_history_permission_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema(engine, group_table: str = "group"):
    metadata = sa.MetaData()
    sa.Table(group_table, metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("identifier", sa.String))
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
    )
    sa.Table("m8flow_tenant", metadata, sa.Column("id", sa.String, primary_key=True))
    metadata.create_all(engine)


def _insert(connection, table: str, rows: list[dict]):
    connection.execute(sa.table(table, *(sa.column(name) for name in rows[0])).insert(), rows)


# Hosts on the renamed authorization table must get the same cleanup.
@pytest.mark.parametrize("group_table", ["group", "m8f_group"])
def test_upgrade_removes_only_tenant_admin_event_history_grants_and_is_idempotent(group_table):
    engine = sa.create_engine("sqlite://")
    _schema(engine, group_table)
    with engine.begin() as connection:
        _insert(
            connection,
            group_table,
            [
                {"id": 1, "identifier": "tenant-a:tenant-admin"},
                {"id": 2, "identifier": "super-admin"},
                {"id": 3, "identifier": "custom:tenant-admin"},  # not a real tenant
                {"id": 4, "identifier": "tenant-a:editor"},
                {"id": 5, "identifier": "tenant-admin"},  # legacy global group
            ],
        )
        _insert(connection, "m8flow_tenant", [{"id": "tenant-a"}])
        _insert(connection, "principal", [{"id": n * 11, "group_id": n} for n in (1, 2, 3, 4, 5)])
        _insert(
            connection,
            "permission_target",
            [
                {"id": 101, "command": "read", "resource_type": "tenant", "resource_id": "/m8flow/nats/events"},
                {"id": 102, "command": "read", "resource_type": "tenant", "resource_id": "/m8flow/nats/events/%"},
                {"id": 103, "command": "read", "resource_type": "tenant", "resource_id": "/m8flow/nats/%"},
                {"id": 104, "command": "read", "resource_type": "tenant", "resource_id": "/m8flow/nats-tokens"},
            ],
        )
        grants = [
            (1, 11, 101),  # tenant-admin events list -> revoked
            (2, 11, 102),  # tenant-admin event by id -> revoked
            (3, 11, 104),  # tenant-admin NATS API keys -> kept
            (4, 22, 101),  # super-admin events -> kept
            (5, 22, 103),  # super-admin monitoring wildcard -> kept
            (6, 33, 101),  # namespaced, not a tenant -> kept
            (7, 44, 101),  # another role -> kept
            (8, 55, 101),  # legacy global tenant-admin events list -> revoked
            (9, 55, 102),  # legacy global tenant-admin event by id -> revoked
        ]
        _insert(
            connection,
            "permission_assignment",
            [
                {"id": i, "principal_id": p, "permission_target_id": t, "grant_type": "permit", "permission": "read"}
                for i, p, t in grants
            ],
        )

        migration = _migration_module()
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()

        remaining = connection.execute(sa.text("SELECT id FROM permission_assignment ORDER BY id")).scalars().all()

    assert remaining == [3, 4, 5, 6, 7]


def test_tenant_admin_group_query_quotes_reserved_group_identifier_for_postgresql():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    _schema(engine)

    with engine.connect() as connection:
        sql = str(migration._tenant_admin_principals_query(connection).compile(dialect=postgresql.dialect()))

    assert 'JOIN "group"' in sql
