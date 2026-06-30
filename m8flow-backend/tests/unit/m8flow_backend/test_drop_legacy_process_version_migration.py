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
    / "n7g8h9i0j1k2_drop_legacy_process_version.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("drop_legacy_process_version_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bind_operations(module, connection: sa.Connection) -> None:
    context = MigrationContext.configure(connection)
    module.op = Operations(context)


def _process_instance_columns(connection: sa.Connection) -> dict[str, dict[str, object]]:
    return {
        column["name"]: column
        for column in sa.inspect(connection).get_columns("process_instance")
    }


def _create_process_instance_schema(connection: sa.Connection, *, include_process_version: bool) -> None:
    metadata = sa.MetaData()
    columns = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=50), nullable=False),
    ]
    if include_process_version:
        columns.append(sa.Column("process_version", sa.Integer(), nullable=False))

    process_instance_table = sa.Table("process_instance", metadata, *columns)
    metadata.create_all(connection)

    insert_payload: dict[str, object] = {"id": 1, "status": "running"}
    if include_process_version:
        insert_payload["process_version"] = 7
    connection.execute(sa.insert(process_instance_table), [insert_payload])


def test_upgrade_drops_legacy_process_version_and_is_idempotent() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        _create_process_instance_schema(connection, include_process_version=True)
        _bind_operations(module, connection)

        module.upgrade()
        _bind_operations(module, connection)
        module.upgrade()

        columns = _process_instance_columns(connection)
        assert set(columns) == {"id", "status"}
        assert "process_version" not in columns

        row = dict(
            connection.execute(
                sa.text("SELECT id, status FROM process_instance WHERE id = 1")
            ).mappings().one()
        )
        assert row == {"id": 1, "status": "running"}


def test_upgrade_is_noop_and_downgrade_restores_process_version_consistently() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        _create_process_instance_schema(connection, include_process_version=False)
        _bind_operations(module, connection)

        module.upgrade()
        assert "process_version" not in _process_instance_columns(connection)

        _bind_operations(module, connection)
        module.downgrade()

        columns = _process_instance_columns(connection)
        assert set(columns) == {"id", "status", "process_version"}
        assert columns["process_version"]["nullable"] is False
        assert columns["process_version"]["default"] is None

        row = dict(
            connection.execute(
                sa.text(
                    "SELECT id, status, process_version FROM process_instance WHERE id = 1"
                )
            ).mappings().one()
        )
        assert row == {"id": 1, "status": "running", "process_version": 1}
