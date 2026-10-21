"""Regression tests for the Task Review/Home permission backfill migration."""

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
    / "b8c9d0e1f2a3_backfill_task_review_home_permissions.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("task_review_home_permission_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema(engine):
    metadata = sa.MetaData()
    sa.Table("m8flow_tenant", metadata, sa.Column("id", sa.String(255), primary_key=True))
    sa.Table(
        "group",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255)),
        sa.Column("identifier", sa.String(255)),
        sa.Column("authorization_key", sa.String(255)),
    )
    sa.Table(
        "principal",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("group_id", sa.Integer),
    )
    sa.Table(
        "permission_target",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("command", sa.String(255), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255)),
    )
    sa.Table(
        "permission_assignment",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("principal_id", sa.Integer, nullable=False),
        sa.Column("permission_target_id", sa.Integer, nullable=False),
        sa.Column("grant_type", sa.String(50), nullable=False),
        sa.Column("permission", sa.String(50), nullable=False),
    )
    sa.Table(
        "m8flow_tenant_permission_seed",
        metadata,
        sa.Column("m8f_tenant_id", sa.String(255), primary_key=True),
        sa.Column("seed_version", sa.Integer, nullable=False),
    )
    metadata.create_all(engine)


def test_upgrade_backfills_existing_roles_idempotently_and_preserves_unmarked_seed_state():
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    migration = _migration_module()

    with engine.begin() as connection:
        groups = sa.Table("group", sa.MetaData(), autoload_with=connection)
        principals = sa.Table("principal", sa.MetaData(), autoload_with=connection)
        targets = sa.Table("permission_target", sa.MetaData(), autoload_with=connection)
        assignments = sa.Table("permission_assignment", sa.MetaData(), autoload_with=connection)
        markers = sa.Table(
            "m8flow_tenant_permission_seed", sa.MetaData(), autoload_with=connection
        )
        tenants = sa.Table("m8flow_tenant", sa.MetaData(), autoload_with=connection)

        connection.execute(
            tenants.insert(),
            [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}, {"id": "t4"}],
        )
        connection.execute(
            groups.insert(),
            [
                {
                    "id": 1,
                    "name": "t1:reviewer",
                    "identifier": "t1:reviewer",
                    "authorization_key": "authorization:t1:reviewer",
                },
                {
                    "id": 2,
                    "name": "t1:reviewer lane",
                    "identifier": "t1:reviewer",
                    "authorization_key": "authorization:lane:2",
                },
                {
                    "id": 3,
                    "name": "t3:reviewer",
                    "identifier": "t3:reviewer",
                    "authorization_key": "authorization:t3:reviewer",
                },
                {
                    "id": 4,
                    "name": "t4:reviewer",
                    "identifier": "t4:reviewer",
                    "authorization_key": "authorization:t4:reviewer",
                },
            ],
        )
        connection.execute(
            principals.insert(),
            [
                {"id": 11, "user_id": None, "group_id": 1},
                {"id": 33, "user_id": None, "group_id": 3},
                {"id": 44, "user_id": None, "group_id": 4},
            ],
        )
        connection.execute(
            targets.insert(),
            [
                {
                    "id": 101,
                    "command": "read",
                    "resource_type": "tenant",
                    "resource_id": "/m8flow/home-task-count",
                }
            ],
        )
        connection.execute(
            assignments.insert(),
            [
                {
                    "id": 201,
                    "principal_id": 11,
                    "permission_target_id": 101,
                    "grant_type": "deny",
                    "permission": "read",
                }
            ],
        )
        connection.execute(
            markers.insert(),
            [
                {"m8f_tenant_id": "t1", "seed_version": 1},
                {"m8f_tenant_id": "t3", "seed_version": 2},
                {"m8f_tenant_id": "t4", "seed_version": 3},
            ],
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()

        role_grants = connection.execute(
            sa.select(
                groups.c.identifier,
                groups.c.authorization_key,
                targets.c.command,
                targets.c.resource_id,
                assignments.c.grant_type,
            )
            .select_from(
                assignments.join(principals, principals.c.id == assignments.c.principal_id)
                .join(groups, groups.c.id == principals.c.group_id)
                .join(targets, targets.c.id == assignments.c.permission_target_id)
            )
            .order_by(groups.c.identifier, targets.c.resource_id)
        ).all()
        marker_rows = connection.execute(
            sa.select(markers.c.m8f_tenant_id, markers.c.seed_version).order_by(
                markers.c.m8f_tenant_id
            )
        ).all()
        target_count = connection.execute(sa.select(sa.func.count()).select_from(targets)).scalar_one()

    assert len(role_grants) == 36  # 3 roles x 4 grants x 3 tenants below v3
    assert target_count == 4
    assert marker_rows == [("t1", 3), ("t3", 3), ("t4", 3)]
    assert all(not row.identifier.startswith("t4:") for row in role_grants)
    assert sum(row.grant_type == "deny" for row in role_grants) == 1
    assert all(
        row.authorization_key != "authorization:lane:2" for row in role_grants
    )
