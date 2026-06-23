from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "l5e6f7a8b9c0_clear_permission_targets_for_command_sync.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("clear_permission_targets_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bind_operations(module, connection: sa.Connection) -> None:
    context = MigrationContext.configure(connection)
    module.op = Operations(context)


def _create_compatible_schema(connection: sa.Connection) -> None:
    metadata = sa.MetaData()

    user_table = sa.Table(
        "user",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
    )
    group_table = sa.Table(
        "group",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
    )
    principal_table = sa.Table(
        "principal",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("group.id"), nullable=True),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND group_id IS NULL) OR (user_id IS NULL AND group_id IS NOT NULL)",
            name="principal_exactly_one_subject",
        ),
    )
    permission_target_table = sa.Table(
        "permission_target",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uri", sa.String(length=255), nullable=False),
        sa.Column("command", sa.String(length=255), nullable=True),
        sa.UniqueConstraint("uri", "command", name="permission_target_uri_command_unique"),
    )
    user_group_assignment_table = sa.Table(
        "user_group_assignment",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("group.id"), nullable=False),
        sa.UniqueConstraint("user_id", "group_id", name="user_group_assignment_unique"),
    )
    permission_assignment_table = sa.Table(
        "permission_assignment",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("principal_id", sa.Integer(), sa.ForeignKey("principal.id"), nullable=False),
        sa.Column("permission_target_id", sa.Integer(), sa.ForeignKey("permission_target.id"), nullable=False),
        sa.Column("grant_type", sa.String(length=50), nullable=False),
        sa.Column("permission", sa.String(length=50), nullable=False),
        sa.UniqueConstraint(
            "principal_id",
            "permission_target_id",
            "permission",
            name="permission_assignment_unique",
        ),
    )

    sa.Index("ix_permission_target_uri", permission_target_table.c.uri)
    sa.Index("ix_permission_target_command", permission_target_table.c.command)
    sa.Index("ix_principal_user_id", principal_table.c.user_id, unique=True)
    sa.Index("ix_principal_group_id", principal_table.c.group_id, unique=True)
    sa.Index("ix_user_group_assignment_user_id", user_group_assignment_table.c.user_id)
    sa.Index("ix_user_group_assignment_group_id", user_group_assignment_table.c.group_id)
    sa.Index("ix_permission_assignment_principal_id", permission_assignment_table.c.principal_id)
    sa.Index("ix_permission_assignment_permission_target_id", permission_assignment_table.c.permission_target_id)

    metadata.create_all(connection)

    connection.execute(sa.insert(user_table), [{"id": 1}])
    connection.execute(sa.insert(group_table), [{"id": 10}])
    connection.execute(
        sa.insert(principal_table),
        [
            {"id": 100, "user_id": 1, "group_id": None},
            {"id": 101, "user_id": None, "group_id": 10},
        ],
    )
    connection.execute(
        sa.insert(permission_target_table),
        [
            {"id": 200, "uri": "/process-models", "command": "process_model.list"},
            {"id": 201, "uri": "/tasks/%", "command": None},
        ],
    )
    connection.execute(
        sa.insert(user_group_assignment_table),
        [{"id": 300, "user_id": 1, "group_id": 10}],
    )
    connection.execute(
        sa.insert(permission_assignment_table),
        [
            {
                "id": 400,
                "principal_id": 100,
                "permission_target_id": 200,
                "grant_type": "permit",
                "permission": "read",
            },
            {
                "id": 401,
                "principal_id": 101,
                "permission_target_id": 201,
                "grant_type": "permit",
                "permission": "read",
            },
        ],
    )


def test_upgrade_clears_permission_targets_and_dependent_assignments_only() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        connection.execute(sa.text("PRAGMA foreign_keys=ON"))
        _create_compatible_schema(connection)
        _bind_operations(module, connection)

        module.upgrade()

        assert connection.execute(sa.text('SELECT COUNT(*) FROM "permission_assignment"')).scalar_one() == 0
        assert connection.execute(sa.text('SELECT COUNT(*) FROM "permission_target"')).scalar_one() == 0
        assert connection.execute(sa.text('SELECT COUNT(*) FROM "principal"')).scalar_one() == 2
        assert connection.execute(sa.text('SELECT COUNT(*) FROM "user_group_assignment"')).scalar_one() == 1
        assert connection.execute(sa.text('SELECT COUNT(*) FROM "user"')).scalar_one() == 1
        assert connection.execute(sa.text('SELECT COUNT(*) FROM "group"')).scalar_one() == 1
