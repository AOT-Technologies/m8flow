"""Tests for tenant-scoped case-insensitive named-value names."""

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
    / "w6x7y8z9a0b1_named_value_name_case_insensitive.py"
)
TABLE = "m8flow_named_value"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("named_value_name_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bind_operations(module, connection: sa.Connection) -> None:
    module.op = Operations(MigrationContext.configure(connection))


def _create_table(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            f"""CREATE TABLE {TABLE} (
                id VARCHAR(36) PRIMARY KEY,
                m8f_tenant_id VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                CONSTRAINT uq_m8flow_named_value_tenant_name UNIQUE (m8f_tenant_id, name)
            )"""
        )
    )


@pytest.fixture
def connection():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        yield connection


def test_upgrade_fails_with_actionable_existing_case_collision(connection):
    module = _load_migration_module()
    _create_table(connection)
    connection.execute(sa.text(f"INSERT INTO {TABLE} VALUES ('1', 'tenant-a', 'Test')"))
    connection.execute(sa.text(f"INSERT INTO {TABLE} VALUES ('2', 'tenant-a', 'TEST')"))
    _bind_operations(module, connection)

    with pytest.raises(RuntimeError, match="tenant-a.*TEST.*Test"):
        module.upgrade()


def test_upgrade_replaces_exact_case_rule_with_functional_unique_index(connection):
    module = _load_migration_module()
    _create_table(connection)
    _bind_operations(module, connection)

    module.upgrade()

    index_names = connection.execute(
        sa.text(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = :table_name"
        ),
        {"table_name": TABLE},
    ).scalars()
    assert module.NEW_INDEX in set(index_names)
    assert not any(
        constraint["name"] == module.OLD_CONSTRAINT
        for constraint in sa.inspect(connection).get_unique_constraints(TABLE)
    )
    connection.execute(sa.text(f"INSERT INTO {TABLE} VALUES ('1', 'tenant-a', 'Test')"))
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text(f"INSERT INTO {TABLE} VALUES ('2', 'tenant-a', 'TEST')"))
    connection.execute(sa.text(f"INSERT INTO {TABLE} VALUES ('3', 'tenant-b', 'TEST')"))


def test_migration_is_last_after_current_head():
    module = _load_migration_module()
    assert module.revision == "w6x7y8z9a0b1"
    assert module.down_revision == "v5w6x7y8z9a0"
