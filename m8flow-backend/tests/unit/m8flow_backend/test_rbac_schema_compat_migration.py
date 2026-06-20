from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "k4d5e6f7a8b9_align_rbac_schema_with_m8flow_bpmn_core.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("rbac_schema_compat_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bind_operations(module, connection: sa.Connection) -> None:
    context = MigrationContext.configure(connection)
    module.op = Operations(context)


def _index_exists(connection: sa.Connection, table_name: str, columns: list[str], *, unique: bool | None = None) -> bool:
    for index in sa.inspect(connection).get_indexes(table_name):
        if list(index.get("column_names") or []) != columns:
            continue
        if unique is None or bool(index.get("unique")) is unique:
            return True
    return False


def _unique_exists(connection: sa.Connection, table_name: str, columns: list[str], *, name: str | None = None) -> bool:
    for constraint in sa.inspect(connection).get_unique_constraints(table_name):
        if list(constraint.get("column_names") or []) != columns:
            continue
        if name is None or constraint.get("name") == name:
            return True
    return False


def _foreign_key_exists(
    connection: sa.Connection,
    table_name: str,
    constrained_columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> bool:
    for foreign_key in sa.inspect(connection).get_foreign_keys(table_name):
        if foreign_key.get("referred_table") != referred_table:
            continue
        if list(foreign_key.get("constrained_columns") or []) != constrained_columns:
            continue
        if list(foreign_key.get("referred_columns") or []) != referred_columns:
            continue
        return True
    return False


def _check_constraint_exists(connection: sa.Connection, table_name: str, *, name: str | None = None, sql_fragment: str | None = None) -> bool:
    for constraint in sa.inspect(connection).get_check_constraints(table_name):
        if name is not None and constraint.get("name") != name:
            continue
        if sql_fragment is not None and sql_fragment not in str(constraint.get("sqltext") or ""):
            continue
        return True
    return False


def _legacy_schema() -> tuple[sa.MetaData, dict[str, sa.Table]]:
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
    permission_target = sa.Table(
        "permission_target",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uri", sa.String(length=255), nullable=False),
        sa.UniqueConstraint("uri"),
    )
    principal = sa.Table(
        "principal",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("group.id"), nullable=True),
        sa.CheckConstraint("NOT(user_id IS NULL AND group_id IS NULL)"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("group_id"),
    )
    user_group_assignment = sa.Table(
        "user_group_assignment",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("group.id"), nullable=False),
        sa.UniqueConstraint("user_id", "group_id", name="user_group_assignment_unique"),
    )
    permission_assignment = sa.Table(
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
            name="permission_assignment_uniq",
        ),
    )

    sa.Index("ix_user_group_assignment_user_id", user_group_assignment.c.user_id)
    sa.Index("ix_user_group_assignment_group_id", user_group_assignment.c.group_id)
    sa.Index("ix_permission_assignment_principal_id", permission_assignment.c.principal_id)
    sa.Index("ix_permission_assignment_permission_target_id", permission_assignment.c.permission_target_id)

    return metadata, {
        "user": user_table,
        "group": group_table,
        "permission_target": permission_target,
        "principal": principal,
        "user_group_assignment": user_group_assignment,
        "permission_assignment": permission_assignment,
    }


def _create_legacy_schema(connection: sa.Connection) -> dict[str, sa.Table]:
    metadata, tables = _legacy_schema()
    metadata.create_all(connection)
    return tables


def _seed_legacy_schema(connection: sa.Connection, tables: dict[str, sa.Table]) -> None:
    connection.execute(sa.insert(tables["user"]), [{"id": 1}, {"id": 2}])
    connection.execute(sa.insert(tables["group"]), [{"id": 10}, {"id": 11}])
    connection.execute(sa.insert(tables["permission_target"]), [{"id": 100, "uri": "/tasks"}])
    connection.execute(
        sa.insert(tables["principal"]),
        [
            {"id": 1000, "user_id": 1, "group_id": None},
            {"id": 1001, "user_id": None, "group_id": 10},
        ],
    )
    connection.execute(sa.insert(tables["user_group_assignment"]), [{"id": 2000, "user_id": 1, "group_id": 10}])
    connection.execute(
        sa.insert(tables["permission_assignment"]),
        [
            {
                "id": 3000,
                "principal_id": 1000,
                "permission_target_id": 100,
                "grant_type": "permit",
                "permission": "read",
            }
        ],
    )


def test_upgrade_aligns_rbac_schema_with_bpmn_core_contract() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        connection.execute(sa.text("PRAGMA foreign_keys=ON"))
        tables = _create_legacy_schema(connection)
        _seed_legacy_schema(connection, tables)
        _bind_operations(module, connection)

        module.upgrade()

        inspector = sa.inspect(connection)
        table_names = set(inspector.get_table_names())
        assert {
            "permission_target",
            "user_group_assignment",
            "principal",
            "permission_assignment",
        }.issubset(table_names)
        assert "permission_target__rbac_compat_old" not in table_names
        assert "principal__rbac_compat_old" not in table_names
        assert "permission_assignment__rbac_compat_old" not in table_names

        permission_target_columns = {column["name"]: column for column in inspector.get_columns("permission_target")}
        assert set(permission_target_columns) == {"id", "uri", "command"}
        assert permission_target_columns["command"]["nullable"] is True
        assert _unique_exists(
            connection,
            "permission_target",
            ["uri", "command"],
            name="permission_target_uri_command_unique",
        )
        assert _index_exists(connection, "permission_target", ["uri"])
        assert _index_exists(connection, "permission_target", ["command"])

        assert _foreign_key_exists(connection, "principal", ["user_id"], "user", ["id"])
        assert _foreign_key_exists(connection, "principal", ["group_id"], "group", ["id"])
        assert _check_constraint_exists(
            connection,
            "principal",
            name="principal_exactly_one_subject",
        )
        assert _index_exists(connection, "principal", ["user_id"], unique=True)
        assert _index_exists(connection, "principal", ["group_id"], unique=True)

        assert _foreign_key_exists(connection, "permission_assignment", ["principal_id"], "principal", ["id"])
        assert _foreign_key_exists(connection, "permission_assignment", ["permission_target_id"], "permission_target", ["id"])
        assert _unique_exists(
            connection,
            "permission_assignment",
            ["principal_id", "permission_target_id", "permission"],
            name="permission_assignment_unique",
        )
        assert _index_exists(connection, "permission_assignment", ["principal_id"])
        assert _index_exists(connection, "permission_assignment", ["permission_target_id"])

        assert _foreign_key_exists(connection, "user_group_assignment", ["user_id"], "user", ["id"])
        assert _foreign_key_exists(connection, "user_group_assignment", ["group_id"], "group", ["id"])
        assert _unique_exists(
            connection,
            "user_group_assignment",
            ["user_id", "group_id"],
            name="user_group_assignment_unique",
        )
        assert _index_exists(connection, "user_group_assignment", ["user_id"])
        assert _index_exists(connection, "user_group_assignment", ["group_id"])

        permission_target_row = dict(
            connection.execute(
                sa.text("SELECT id, uri, command FROM permission_target WHERE id = 100")
            ).mappings().one()
        )
        assert permission_target_row == {"id": 100, "uri": "/tasks", "command": None}

        principal_rows = [
            dict(row)
            for row in connection.execute(
                sa.text("SELECT id, user_id, group_id FROM principal ORDER BY id")
            ).mappings().all()
        ]
        assert principal_rows == [
            {"id": 1000, "user_id": 1, "group_id": None},
            {"id": 1001, "user_id": None, "group_id": 10},
        ]

        permission_assignment_rows = [
            dict(row)
            for row in connection.execute(
                sa.text(
                    """
                    SELECT id, principal_id, permission_target_id, grant_type, permission
                    FROM permission_assignment
                    ORDER BY id
                    """
                )
            ).mappings().all()
        ]
        assert permission_assignment_rows == [
            {
                "id": 3000,
                "principal_id": 1000,
                "permission_target_id": 100,
                "grant_type": "permit",
                "permission": "read",
            }
        ]


def test_downgrade_restores_legacy_rbac_shape_when_uris_are_unique() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        connection.execute(sa.text("PRAGMA foreign_keys=ON"))
        tables = _create_legacy_schema(connection)
        _seed_legacy_schema(connection, tables)
        _bind_operations(module, connection)
        module.upgrade()

        _bind_operations(module, connection)
        module.downgrade()

        inspector = sa.inspect(connection)
        table_names = set(inspector.get_table_names())
        assert "permission_target__rbac_compat_new" not in table_names
        assert "principal__rbac_compat_new" not in table_names
        assert "permission_assignment__rbac_compat_new" not in table_names

        permission_target_columns = {column["name"] for column in inspector.get_columns("permission_target")}
        assert permission_target_columns == {"id", "uri"}
        assert _unique_exists(connection, "permission_target", ["uri"])

        assert _check_constraint_exists(
            connection,
            "principal",
            sql_fragment="NOT(user_id IS NULL AND group_id IS NULL)",
        )
        assert _unique_exists(
            connection,
            "permission_assignment",
            ["principal_id", "permission_target_id", "permission"],
            name="permission_assignment_uniq",
        )
        assert _index_exists(connection, "permission_assignment", ["principal_id"])
        assert _index_exists(connection, "permission_assignment", ["permission_target_id"])

        permission_target_row = dict(
            connection.execute(
                sa.text("SELECT id, uri FROM permission_target WHERE id = 100")
            ).mappings().one()
        )
        assert permission_target_row == {"id": 100, "uri": "/tasks"}


def test_upgrade_fails_fast_for_principal_rows_that_set_both_user_and_group() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        connection.execute(sa.text("PRAGMA foreign_keys=ON"))
        tables = _create_legacy_schema(connection)
        connection.execute(sa.insert(tables["user"]), [{"id": 1}])
        connection.execute(sa.insert(tables["group"]), [{"id": 10}])
        connection.execute(sa.insert(tables["permission_target"]), [{"id": 100, "uri": "/tasks"}])
        connection.execute(
            sa.insert(tables["principal"]),
            [{"id": 1000, "user_id": 1, "group_id": 10}],
        )
        _bind_operations(module, connection)

        with pytest.raises(RuntimeError, match="exactly-one-of\\(user_id, group_id\\)"):
            module.upgrade()
