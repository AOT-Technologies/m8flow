"""Epoch -> native timestamp backfill in c3d4e5f6a7b8: pin the SQL each dialect gets.

The UPDATE is built with SQLAlchemy Core (not an f-string); run it in Alembic offline (--sql)
mode and check the statement shape per dialect, plus real rows on SQLite.
"""

from __future__ import annotations

import importlib.util
import io
import re
import types
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import mysql, postgresql, sqlite

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "c3d4e5f6a7b8_remove_host_epoch_timestamp_columns.py"
)
_DIALECTS = {"postgresql": postgresql, "mysql": mysql, "sqlite": sqlite}
_EXPECTED_SET = {
    "postgresql": "to_timestamp(created_at_in_seconds)",
    "mysql": "FROM_UNIXTIME(created_at_in_seconds)",
    "sqlite": "datetime(created_at_in_seconds, 'unixepoch')",
}


def _load():
    spec = importlib.util.spec_from_file_location("c3d4_backfill", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("dialect", sorted(_DIALECTS))
def test_backfill_update_offline(dialect):
    migration = _load()
    real_op = migration.op
    fake_bind = types.SimpleNamespace(dialect=_DIALECTS[dialect].dialect())
    migration.op = types.SimpleNamespace(execute=lambda stmt: real_op.execute(stmt), get_bind=lambda: fake_bind)

    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name=dialect, opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True}
    )
    with Operations.context(context):
        migration._backfill_native_columns("group", ("created_at_in_seconds",))

    # Drop table qualification/quoting so the check is about the statement, not formatting.
    sql = re.sub(r'[`"]?group[`"]?\.', "", buffer.getvalue())
    sql = re.sub(r"\s+", " ", sql.replace('"', "").replace("`", ""))
    assert f"UPDATE group SET created_at={_EXPECTED_SET[dialect]}" in sql
    assert "WHERE created_at IS NULL AND created_at_in_seconds IS NOT NULL" in sql


def test_backfill_fills_only_missing_values_on_sqlite():
    migration = _load()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            'CREATE TABLE "group" (id INTEGER PRIMARY KEY, created_at_in_seconds INTEGER, created_at DATETIME)'
        )
        connection.exec_driver_sql(
            "INSERT INTO \"group\" VALUES (1, 0, NULL), (2, NULL, NULL), (3, 0, '2020-01-01 00:00:00')"
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration._backfill_native_columns("group", ("created_at_in_seconds",))
        rows = connection.exec_driver_sql('SELECT id, created_at FROM "group" ORDER BY id').all()
    assert rows == [(1, "1970-01-01 00:00:00"), (2, None), (3, "2020-01-01 00:00:00")]
