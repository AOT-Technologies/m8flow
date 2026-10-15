"""Regression tests for revoking editor access to Home task counts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "f6a7b8c9d0e1_revoke_editor_home_task_count.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("home_task_count_permission_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema(engine):
    metadata = sa.MetaData()
    sa.Table(
        "group", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("identifier", sa.String)
    )
    sa.Table(
        "principal", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("group_id", sa.Integer)
    )
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
    metadata.create_all(engine)


def test_upgrade_removes_only_editor_home_task_count_read_grants_and_is_idempotent():
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    with engine.begin() as connection:
        connection.execute(
            sa.table("group", sa.column("id"), sa.column("identifier")).insert(),
            [
                {"id": 1, "identifier": "tenant-a:editor"},
                {"id": 2, "identifier": "tenant-a:reviewer"},
            ],
        )
        connection.execute(
            sa.table("principal", sa.column("id"), sa.column("group_id")).insert(),
            [{"id": 11, "group_id": 1}, {"id": 22, "group_id": 2}],
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
                {
                    "id": 101,
                    "command": "read",
                    "resource_type": "tenant",
                    "resource_id": "/m8flow/home-task-count",
                },
                {
                    "id": 102,
                    "command": "read",
                    "resource_type": "tenant",
                    "resource_id": "/m8flow/other-read",
                },
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
                {
                    "id": 1,
                    "principal_id": 11,
                    "permission_target_id": 101,
                    "grant_type": "permit",
                    "permission": "read",
                },
                {
                    "id": 2,
                    "principal_id": 22,
                    "permission_target_id": 101,
                    "grant_type": "permit",
                    "permission": "read",
                },
                {
                    "id": 3,
                    "principal_id": 11,
                    "permission_target_id": 102,
                    "grant_type": "permit",
                    "permission": "read",
                },
            ],
        )

        migration = _migration_module()
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()

        remaining = connection.execute(
            sa.text("SELECT id FROM permission_assignment ORDER BY id")
        ).scalars().all()

    assert remaining == [2, 3]
