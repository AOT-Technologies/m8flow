"""Unit tests for the add-last_error migration (r1k2l3m4n5o6).

Tests cover:
- upgrade adds a nullable last_error column and preserves existing rows
- upgrade is idempotent when the column already exists
- upgrade is a no-op when the table is absent
- downgrade removes the column and is idempotent
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "r1k2l3m4n5o6_add_external_form_request_last_error.py"
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


def _columns(connection: sa.Connection) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(connection).get_columns(TABLE_NAME)}


def _create_pre_migration_table(connection: sa.Connection) -> None:
    """The table as it stood before this revision: no last_error column."""
    connection.execute(
        sa.text(
            f"""
            CREATE TABLE {TABLE_NAME} (
                id INTEGER NOT NULL PRIMARY KEY,
                reference_id VARCHAR(255) NOT NULL,
                process_instance_id INTEGER NOT NULL,
                task_guid VARCHAR(36) NOT NULL,
                recipient_user_id INTEGER NOT NULL,
                email VARCHAR(255) NOT NULL,
                external_form_url TEXT NOT NULL,
                status VARCHAR(32) NOT NULL,
                attempts INTEGER NOT NULL,
                notified_at_in_seconds INTEGER,
                m8f_tenant_id VARCHAR(255)
            )
            """
        )
    )
    connection.execute(
        sa.text(
            f"""
            INSERT INTO {TABLE_NAME}
                (id, reference_id, process_instance_id, task_guid, recipient_user_id,
                 email, external_form_url, status, attempts, m8f_tenant_id)
            VALUES
                (1, 'ref-1', 42, 'task-guid', 7, 'alice@example.com',
                 'https://forms.example.com/f', 'pending', 0, 'tenant-1')
            """
        )
    )


@pytest.fixture
def connection():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        yield connection


def test_upgrade_adds_nullable_column_and_keeps_rows(connection):
    module = _load_migration_module()
    _create_pre_migration_table(connection)
    _bind_operations(module, connection)

    module.upgrade()

    columns = _columns(connection)
    assert "last_error" in columns
    assert columns["last_error"]["nullable"] is True
    # Existing data survives and reads back as NULL.
    row = connection.execute(sa.text(f"SELECT id, status, last_error FROM {TABLE_NAME}")).fetchone()
    assert row == (1, "pending", None)


def test_upgrade_is_idempotent(connection):
    module = _load_migration_module()
    _create_pre_migration_table(connection)
    _bind_operations(module, connection)

    module.upgrade()
    module.upgrade()

    assert "last_error" in _columns(connection)


def test_upgrade_is_a_noop_without_the_table(connection):
    module = _load_migration_module()
    _bind_operations(module, connection)

    module.upgrade()

    assert TABLE_NAME not in sa.inspect(connection).get_table_names()


def test_downgrade_removes_the_column(connection):
    module = _load_migration_module()
    _create_pre_migration_table(connection)
    _bind_operations(module, connection)
    module.upgrade()

    module.downgrade()

    assert "last_error" not in _columns(connection)
    # Dropping diagnostic text must not drop request state.
    row = connection.execute(sa.text(f"SELECT id, status FROM {TABLE_NAME}")).fetchone()
    assert row == (1, "pending")


def test_downgrade_is_idempotent(connection):
    module = _load_migration_module()
    _create_pre_migration_table(connection)
    _bind_operations(module, connection)
    module.upgrade()

    module.downgrade()
    module.downgrade()

    assert "last_error" not in _columns(connection)


def test_revision_chains_onto_the_previous_head(connection):
    module = _load_migration_module()

    assert module.revision == "r1k2l3m4n5o6"
    # Chains after the audit-log migration so this branch remains linear.
    assert module.down_revision == "q1r2s3t4u5v6"
