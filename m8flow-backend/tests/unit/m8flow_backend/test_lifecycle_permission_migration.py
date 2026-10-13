"""Tests for the lifecycle permission compatibility migration."""

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
    / "e7f8a9b0c1d2_backfill_lifecycle_execute_permissions.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("lifecycle_permission_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(connection) -> None:
    migration = _migration_module()
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        migration.upgrade()


def _schema(engine):
    metadata = sa.MetaData()
    sa.Table(
        "permission_target",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("command", sa.String(100)),
    )
    sa.Table(
        "permission_assignment",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("principal_id", sa.Integer, nullable=False),
        sa.Column("permission_target_id", sa.Integer, nullable=False),
        sa.Column("grant_type", sa.String(50), nullable=False),
        sa.Column("permission", sa.String(50), nullable=False),
        sa.UniqueConstraint(
            "principal_id",
            "permission_target_id",
            "permission",
            name="permission_assignment_unique",
        ),
    )
    metadata.create_all(engine)


def test_upgrade_backfills_lifecycle_execute_grants_and_is_idempotent():
    engine = sa.create_engine("sqlite://")
    _schema(engine)

    with engine.begin() as connection:
        connection.execute(
            sa.table("permission_target", sa.column("id"), sa.column("command")).insert(),
            [
                {"id": 1, "command": "process.suspend"},
                {"id": 2, "command": "process.resume"},
                {"id": 3, "command": "process.start"},
            ],
        )
        connection.execute(
            sa.table(
                "permission_assignment",
                sa.column("principal_id"),
                sa.column("permission_target_id"),
                sa.column("grant_type"),
                sa.column("permission"),
            ).insert(),
            [
                {
                    "principal_id": 10,
                    "permission_target_id": 1,
                    "grant_type": "permit",
                    "permission": "create",
                },
                {
                    "principal_id": 10,
                    "permission_target_id": 2,
                    "grant_type": "deny",
                    "permission": "create",
                },
                {
                    "principal_id": 10,
                    "permission_target_id": 3,
                    "grant_type": "permit",
                    "permission": "create",
                },
                {
                    "principal_id": 20,
                    "permission_target_id": 1,
                    "grant_type": "permit",
                    "permission": "execute",
                },
            ],
        )

        _run_upgrade(connection)
        _run_upgrade(connection)

        rows = connection.execute(
            sa.text(
                "SELECT principal_id, permission_target_id, grant_type, permission "
                "FROM permission_assignment ORDER BY principal_id, permission_target_id, permission"
            )
        ).mappings().all()

    assert rows == [
        {
            "principal_id": 10,
            "permission_target_id": 1,
            "grant_type": "permit",
            "permission": "create",
        },
        {
            "principal_id": 10,
            "permission_target_id": 1,
            "grant_type": "permit",
            "permission": "execute",
        },
        {
            "principal_id": 10,
            "permission_target_id": 2,
            "grant_type": "deny",
            "permission": "create",
        },
        {
            "principal_id": 10,
            "permission_target_id": 2,
            "grant_type": "deny",
            "permission": "execute",
        },
        {
            "principal_id": 10,
            "permission_target_id": 3,
            "grant_type": "permit",
            "permission": "create",
        },
        {
            "principal_id": 20,
            "permission_target_id": 1,
            "grant_type": "permit",
            "permission": "execute",
        },
    ]
