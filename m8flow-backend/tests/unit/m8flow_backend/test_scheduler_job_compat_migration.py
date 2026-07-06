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
    / "m6f7a8b9c0d1_add_scheduler_job_table_compat.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("scheduler_job_compat_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bind_operations(module, connection: sa.Connection) -> None:
    context = MigrationContext.configure(connection)
    module.op = Operations(context)


def _index_exists(connection: sa.Connection, table_name: str, columns: list[str]) -> bool:
    for index in sa.inspect(connection).get_indexes(table_name):
        if list(index.get("column_names") or []) == columns:
            return True
    return False


def _unique_exists(connection: sa.Connection, table_name: str, columns: list[str]) -> bool:
    for constraint in sa.inspect(connection).get_unique_constraints(table_name):
        if list(constraint.get("column_names") or []) == columns:
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


def _create_supporting_schema(connection: sa.Connection) -> None:
    metadata = sa.MetaData()

    tenant_table = sa.Table(
        "m8flow_tenant",
        metadata,
        sa.Column("id", sa.String(length=255), primary_key=True),
    )
    bpmn_process_definition_table = sa.Table(
        "bpmn_process_definition",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
    )
    process_instance_table = sa.Table(
        "process_instance",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
    )

    metadata.create_all(connection)
    connection.execute(sa.insert(tenant_table), [{"id": "tenant-a"}])
    connection.execute(sa.insert(bpmn_process_definition_table), [{"id": 1}])
    connection.execute(sa.insert(process_instance_table), [{"id": 2}])


def test_upgrade_creates_scheduler_job_schema_and_is_idempotent() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        connection.execute(sa.text("PRAGMA foreign_keys=ON"))
        _create_supporting_schema(connection)
        _bind_operations(module, connection)

        module.upgrade()
        _bind_operations(module, connection)
        module.upgrade()

        inspector = sa.inspect(connection)
        assert "scheduler_job" in set(inspector.get_table_names())

        scheduler_job_columns = {column["name"] for column in inspector.get_columns("scheduler_job")}
        assert scheduler_job_columns == {
            "id",
            "job_key",
            "job_type",
            "process_instance_id",
            "bpmn_process_definition_id",
            "locked_by",
            "locked_at_in_seconds",
            "run_at_in_seconds",
            "payload_json",
            "updated_at_in_seconds",
            "created_at_in_seconds",
            "m8f_tenant_id",
        }
        assert _unique_exists(connection, "scheduler_job", ["m8f_tenant_id", "job_key"])
        assert _foreign_key_exists(
            connection,
            "scheduler_job",
            ["bpmn_process_definition_id"],
            "bpmn_process_definition",
            ["id"],
        )
        assert _foreign_key_exists(
            connection,
            "scheduler_job",
            ["m8f_tenant_id"],
            "m8flow_tenant",
            ["id"],
        )
        assert _foreign_key_exists(
            connection,
            "scheduler_job",
            ["process_instance_id"],
            "process_instance",
            ["id"],
        )

        for index_columns in (
            ["bpmn_process_definition_id"],
            ["job_type"],
            ["locked_at_in_seconds"],
            ["locked_by"],
            ["m8f_tenant_id"],
            ["process_instance_id"],
            ["run_at_in_seconds"],
        ):
            assert _index_exists(connection, "scheduler_job", index_columns)

        _bind_operations(module, connection)
        module.downgrade()

        assert "scheduler_job" not in set(sa.inspect(connection).get_table_names())


def test_upgrade_fails_fast_for_incompatible_existing_scheduler_job_table() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        metadata = sa.MetaData()
        sa.Table(
            "scheduler_job",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
        )
        metadata.create_all(connection)
        _bind_operations(module, connection)

        with pytest.raises(RuntimeError, match="existing scheduler_job table is incompatible"):
            module.upgrade()
