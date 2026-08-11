"""Migration test for q0j1k2l3m4n5 (external form request last_error).

Verifies that adding the diagnostic column is idempotent, preserves existing rows, and
round-trips through downgrade — the column is additive, so an upgrade must never disturb
in-flight notification requests.
"""

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
    / "q0j1k2l3m4n5_add_external_form_request_last_error.py"
)

TABLE_NAME = "m8flow_external_form_requests"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("external_form_last_error_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bind_operations(module, connection: sa.Connection) -> None:
    context = MigrationContext.configure(connection)
    module.op = Operations(context)


def _create_supporting_schema(connection: sa.Connection) -> sa.Table:
    """The pre-migration shape of the tracking table, per k3c4d5e6f7a9."""
    metadata = sa.MetaData()
    table = sa.Table(
        TABLE_NAME,
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("reference_id", sa.String(length=255), nullable=False),
        sa.Column("process_instance_id", sa.Integer(), nullable=False),
        sa.Column("task_guid", sa.String(length=36), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("external_form_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("notified_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
    )
    metadata.create_all(connection)
    connection.execute(
        sa.insert(table),
        [
            {
                "id": 1,
                "m8f_tenant_id": "tenant-a",
                "reference_id": "ref-1",
                "process_instance_id": 42,
                "task_guid": "11111111-2222-3333-4444-555555555555",
                "recipient_user_id": 7,
                "email": "alice@example.com",
                "external_form_url": "https://forms.example.com/x",
                "status": "pending",
                "attempts": 0,
                "notified_at_in_seconds": None,
                "created_at_in_seconds": 1000,
                "updated_at_in_seconds": 1000,
            }
        ],
    )
    return table


def _columns(connection: sa.Connection) -> set[str]:
    return {column["name"] for column in sa.inspect(connection).get_columns(TABLE_NAME)}


def test_revision_chains_onto_the_current_head() -> None:
    module = _load_migration_module()

    assert module.revision == "q0j1k2l3m4n5"
    assert module.down_revision == "p9i0j1k2l3m4"


def test_upgrade_adds_nullable_column_idempotently_and_preserves_rows() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        _create_supporting_schema(connection)
        _bind_operations(module, connection)

        module.upgrade()
        _bind_operations(module, connection)
        module.upgrade()  # re-running must be a no-op, not an error

        assert "last_error" in _columns(connection)

        column = next(
            item for item in sa.inspect(connection).get_columns(TABLE_NAME) if item["name"] == "last_error"
        )
        assert column["nullable"] is True

        row = connection.execute(
            sa.text(f"SELECT reference_id, status, last_error FROM {TABLE_NAME} WHERE id = 1")  # noqa: S608
        ).one()
        assert row.reference_id == "ref-1"
        assert row.status == "pending"
        assert row.last_error is None


def test_downgrade_removes_the_column_and_keeps_request_state() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    module = _load_migration_module()

    with engine.begin() as connection:
        _create_supporting_schema(connection)
        _bind_operations(module, connection)
        module.upgrade()

        _bind_operations(module, connection)
        connection.execute(sa.text(f"UPDATE {TABLE_NAME} SET last_error = 'boom' WHERE id = 1"))  # noqa: S608
        module.downgrade()

        assert "last_error" not in _columns(connection)
        row = connection.execute(
            sa.text(f"SELECT reference_id, status FROM {TABLE_NAME} WHERE id = 1")  # noqa: S608
        ).one()
        assert row.reference_id == "ref-1"
        assert row.status == "pending"

        _bind_operations(module, connection)
        module.downgrade()  # idempotent in both directions
        assert "last_error" not in _columns(connection)
