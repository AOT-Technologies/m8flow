from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "d2f4a6b8c0e1_add_configuration_variable_schema.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("configuration_variable_migration", _PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(connection) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        _migration().upgrade()


def _downgrade(connection) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        _migration().downgrade()


def _legacy_schema(connection) -> None:
    connection.exec_driver_sql("CREATE TABLE m8flow_tenant (id VARCHAR(255) PRIMARY KEY)")
    connection.exec_driver_sql("CREATE TABLE user (id INTEGER PRIMARY KEY)")
    connection.exec_driver_sql(
        """CREATE TABLE m8flow_connector_configuration (
            id INTEGER PRIMARY KEY,
            m8f_tenant_id VARCHAR(255) NOT NULL,
            connector_type VARCHAR(50) NOT NULL,
            profile_name VARCHAR(255) NOT NULL,
            config_json JSON NOT NULL,
            secret_refs JSON NOT NULL,
            created_by_user_id INTEGER,
            created_at DATETIME,
            updated_at DATETIME
        )"""
    )
    connection.exec_driver_sql(
        """CREATE TABLE secret (
            id INTEGER PRIMARY KEY,
            key VARCHAR(255) NOT NULL,
            value TEXT NOT NULL,
            m8f_tenant_id VARCHAR(255) NOT NULL,
            created_by_user_id INTEGER,
            created_at DATETIME,
            updated_at DATETIME
        )"""
    )
    connection.exec_driver_sql("INSERT INTO m8flow_tenant (id) VALUES ('tenant-a')")
    connection.exec_driver_sql("INSERT INTO user (id) VALUES (7)")


def test_upgrade_preserves_legacy_rows_and_backfills_safe_metadata():
    with sa.create_engine("sqlite://").begin() as connection:
        _legacy_schema(connection)
        connection.exec_driver_sql(
            """INSERT INTO m8flow_connector_configuration
               (id, m8f_tenant_id, connector_type, profile_name, config_json, secret_refs, created_by_user_id)
               VALUES (3, 'tenant-a', 'http', 'dev', '{"host":"localhost","port":null}',
                       '{"password":"cnx_3_password"}', 7)"""
        )
        connection.exec_driver_sql(
            "INSERT INTO secret (id, key, value, m8f_tenant_id, created_by_user_id) "
            "VALUES (1, 'API_TOKEN', 'encrypted-payload', 'tenant-a', 7)"
        )

        _upgrade(connection)

        named_value = connection.execute(
            sa.text(
                "SELECT name, is_sensitive, value, is_configured, provider_key "
                "FROM m8flow_named_value"
            )
        ).one()
        assert tuple(named_value) == ("API_TOKEN", 1, None, 1, "API_TOKEN")

        variables = {
            row.field_name: row
            for row in connection.execute(
                sa.text(
                    "SELECT field_name, is_sensitive, value, is_configured, provider_key "
                    "FROM m8flow_connector_variable"
                )
            )
        }
        assert variables["host"].value == '"localhost"'
        assert variables["port"].value is None
        assert variables["port"].is_configured == 0
        assert variables["password"].is_sensitive == 1
        assert variables["password"].value is None
        assert variables["password"].is_configured == 0
        assert variables["password"].provider_key == "cnx_3_password"

        legacy = connection.execute(
            sa.text("SELECT config_json, secret_refs FROM m8flow_connector_configuration WHERE id = 3")
        ).one()
        assert legacy.config_json == '{"host":"localhost","port":null}'
        assert legacy.secret_refs == '{"password":"cnx_3_password"}'
        assert connection.execute(sa.text("SELECT value FROM secret WHERE id = 1")).scalar_one() == (
            "encrypted-payload"
        )


def test_upgrade_rejects_case_insensitive_legacy_name_collision_before_schema_changes():
    with sa.create_engine("sqlite://").begin() as connection:
        _legacy_schema(connection)
        connection.exec_driver_sql(
            "INSERT INTO secret (id, key, value, m8f_tenant_id) "
            "VALUES (1, 'ApiToken', 'encrypted-a', 'tenant-a'), "
            "(2, 'apitoken', 'encrypted-b', 'tenant-a')"
        )

        with pytest.raises(RuntimeError, match="case-insensitive configuration-variable names"):
            _upgrade(connection)

        assert "m8flow_named_value" not in sa.inspect(connection).get_table_names()
        assert "provider_key" not in {c["name"] for c in sa.inspect(connection).get_columns(
            "m8flow_connector_configuration"
        )}


def test_downgrade_refuses_to_drop_backfilled_data():
    with sa.create_engine("sqlite://").begin() as connection:
        _legacy_schema(connection)
        connection.exec_driver_sql(
            "INSERT INTO secret (id, key, value, m8f_tenant_id) "
            "VALUES (1, 'API_TOKEN', 'encrypted-payload', 'tenant-a')"
        )
        _upgrade(connection)
        with pytest.raises(RuntimeError, match="Refusing to drop m8flow_named_value"):
            _downgrade(connection)
        assert "m8flow_named_value" in sa.inspect(connection).get_table_names()


def test_empty_schema_downgrade_removes_only_additive_schema():
    with sa.create_engine("sqlite://").begin() as connection:
        _legacy_schema(connection)
        _upgrade(connection)
        _downgrade(connection)
        tables = set(sa.inspect(connection).get_table_names())
        assert "m8flow_named_value" not in tables
        assert "m8flow_connector_variable" not in tables
        assert "secret" in tables
        assert "provider_key" not in {
            c["name"] for c in sa.inspect(connection).get_columns("m8flow_connector_configuration")
        }
