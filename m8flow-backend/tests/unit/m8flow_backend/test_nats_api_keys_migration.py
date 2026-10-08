"""7d4b1e9c3a20 replaces the unused ``m8flow_nats_api_key`` placeholder with ``m8flow_nats_api_keys``.

Nothing in the host, the core wheel, the NATS consumer or the MCP server reads the
placeholder (``NatsTokenService`` maps ``m8flow_nats_api_keys``), so it is dropped,
but only while empty: a placeholder holding rows is left untouched for an operator.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "7d4b1e9c3a20_nats_api_keys_full_schema.py"
)


def _upgrade(connection) -> None:
    spec = importlib.util.spec_from_file_location("nats_api_keys_migration", _PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()


def _with_placeholder(connection, *, rows: int) -> None:
    connection.execute(
        sa.text(
            "CREATE TABLE m8flow_nats_api_key (id INTEGER PRIMARY KEY, key_hash VARCHAR, name VARCHAR)"
        )
    )
    for i in range(rows):
        connection.execute(
            sa.text(
                "INSERT INTO m8flow_nats_api_key (id, key_hash, name) VALUES (:i, 'h', 'n')"
            ),
            {"i": i},
        )


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def test_empty_placeholder_is_dropped_and_real_table_created():
    with sa.create_engine("sqlite://").begin() as connection:
        _with_placeholder(connection, rows=0)
        _upgrade(connection)
        assert "m8flow_nats_api_key" not in _tables(connection)
        assert "m8flow_nats_api_keys" in _tables(connection)


def test_placeholder_with_rows_is_left_untouched():
    with sa.create_engine("sqlite://").begin() as connection:
        _with_placeholder(connection, rows=2)
        _upgrade(connection)
        assert (
            connection.execute(
                sa.text("SELECT COUNT(*) FROM m8flow_nats_api_key")
            ).scalar_one()
            == 2
        )
        assert "m8flow_nats_api_keys" in _tables(connection)


def test_fresh_database_without_placeholder_is_a_no_op():
    with sa.create_engine("sqlite://").begin() as connection:
        _upgrade(connection)
        _upgrade(connection)
        assert "m8flow_nats_api_keys" in _tables(connection)
        assert "m8flow_nats_api_key" not in _tables(connection)
