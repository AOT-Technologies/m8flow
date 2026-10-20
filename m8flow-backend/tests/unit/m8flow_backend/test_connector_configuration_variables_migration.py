"""Tests for the additive connector field metadata migration."""

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
    / "t3u4v5w6x7y8_add_connector_configuration_variables.py"
)
CONFIGURATION_TABLE = "m8flow_connector_configuration"
VARIABLE_TABLE = "m8flow_connector_variable"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("connector_configuration_variables_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bind_operations(module, connection: sa.Connection) -> None:
    module.op = Operations(MigrationContext.configure(connection))


def _create_pre_migration_tables(connection: sa.Connection) -> None:
    connection.execute(sa.text("CREATE TABLE m8flow_tenant (id VARCHAR(255) PRIMARY KEY)"))
    connection.execute(sa.text("CREATE TABLE user (id INTEGER PRIMARY KEY)"))
    connection.execute(
        sa.text(
            f"""
            CREATE TABLE {CONFIGURATION_TABLE} (
                id INTEGER PRIMARY KEY,
                m8f_tenant_id VARCHAR(255) NOT NULL,
                connector_type VARCHAR(50) NOT NULL,
                profile_name VARCHAR(255) NOT NULL,
                display_name VARCHAR(255) NOT NULL,
                description TEXT,
                config_json JSON NOT NULL,
                secret_refs JSON NOT NULL,
                is_active BOOLEAN NOT NULL,
                user_id INTEGER,
                created_at_in_seconds INTEGER NOT NULL,
                updated_at_in_seconds INTEGER NOT NULL
            )
            """
        )
    )


@pytest.fixture
def connection():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        yield connection


def test_upgrade_adds_provider_metadata_and_variable_table(connection):
    module = _load_migration_module()
    _create_pre_migration_tables(connection)
    _bind_operations(module, connection)

    module.upgrade()

    parent_columns = {
        column["name"]: column
        for column in sa.inspect(connection).get_columns(CONFIGURATION_TABLE)
    }
    assert parent_columns["provider_key"]["nullable"] is True
    assert parent_columns["schema_version"]["nullable"] is True

    variable_columns = {
        column["name"]: column
        for column in sa.inspect(connection).get_columns(VARIABLE_TABLE)
    }
    assert variable_columns["value"]["nullable"] is True
    assert variable_columns["is_sensitive"]["nullable"] is False
    assert variable_columns["is_configured"]["nullable"] is False

    constraints = sa.inspect(connection).get_unique_constraints(VARIABLE_TABLE)
    assert any(constraint["name"] == "uq_m8flow_connector_variable_field" for constraint in constraints)


def test_sensitive_variable_cannot_store_a_database_value(connection):
    module = _load_migration_module()
    _create_pre_migration_tables(connection)
    _bind_operations(module, connection)
    module.upgrade()
    connection.execute(sa.text("INSERT INTO m8flow_tenant (id) VALUES ('tenant-1')"))
    connection.execute(sa.text("INSERT INTO user (id) VALUES (1)"))
    connection.execute(
        sa.text(
            f"""
            INSERT INTO {CONFIGURATION_TABLE}
                (id, m8f_tenant_id, connector_type, profile_name, display_name,
                 config_json, secret_refs, is_active, created_at_in_seconds, updated_at_in_seconds)
            VALUES (1, 'tenant-1', 'smtp', 'primary', 'Primary', '{{}}', '{{}}', 1, 1, 1)
            """
        )
    )

    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(
            sa.text(
                f"""
                INSERT INTO {VARIABLE_TABLE}
                    (m8f_tenant_id, connector_configuration_id, field_name,
                     is_sensitive, value, is_configured, created_at_in_seconds, updated_at_in_seconds)
                VALUES ('tenant-1', 1, 'password', 1, '"not-allowed"', 1, 1, 1)
                """
            )
        )


def test_downgrade_removes_only_new_storage_structure(connection):
    module = _load_migration_module()
    _create_pre_migration_tables(connection)
    _bind_operations(module, connection)
    module.upgrade()

    module.downgrade()

    assert VARIABLE_TABLE not in sa.inspect(connection).get_table_names()
    parent_columns = {column["name"] for column in sa.inspect(connection).get_columns(CONFIGURATION_TABLE)}
    assert "provider_key" not in parent_columns
    assert "schema_version" not in parent_columns


def test_revision_chains_onto_previous_head():
    module = _load_migration_module()

    assert module.revision == "t3u4v5w6x7y8"
    assert module.down_revision == "s2l3m4n5o6p7"
