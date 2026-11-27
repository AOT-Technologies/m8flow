"""composite index for the Processes page run stats."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "e9c4b2a71f53_process_instance_run_stats_index.py"
)
_INDEX = "ix_process_instance_tenant_model_started"


def _migration():
    spec = importlib.util.spec_from_file_location("run_stats_index", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine_with_process_instance():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table(
        "process_instance",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
        sa.Column("process_model_identifier", sa.String(255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    return engine


def _apply(engine, operation: str) -> None:
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        getattr(_migration(), operation)()


def _indexes(engine) -> dict[str, list[str]]:
    return {
        index["name"]: index["column_names"]
        for index in sa.inspect(engine).get_indexes("process_instance")
    }


def test_upgrade_creates_the_run_stats_index_and_is_idempotent():
    engine = _engine_with_process_instance()

    _apply(engine, "upgrade")
    _apply(engine, "upgrade")

    assert _indexes(engine)[_INDEX] == ["m8f_tenant_id", "process_model_identifier", "started_at"]


def test_downgrade_drops_only_the_run_stats_index_and_is_idempotent():
    engine = _engine_with_process_instance()
    _apply(engine, "upgrade")

    _apply(engine, "downgrade")
    _apply(engine, "downgrade")

    assert _INDEX not in _indexes(engine)


def test_migration_follows_the_current_head():
    assert _migration().down_revision == "c7e9a1b3d5f7"
    assert _migration().revision == "e9c4b2a71f53"


# PostgreSQL path: CONCURRENTLY, invalid-index recovery, schema scoping. Runs only
# against a disposable database, like test_migration_bootstrap.py's RLS checks.
_PG_URI = os.environ.get("M8FLOW_TEST_POSTGRES_URI")
_needs_postgres = pytest.mark.skipif(
    not _PG_URI, reason="Set M8FLOW_TEST_POSTGRES_URI to a disposable database."
)
_PREVIOUS = "9f2c6d4b8e71"
_HEAD = "e9c4b2a71f53"


def _alembic(monkeypatch) -> Config:
    monkeypatch.setenv("M8FLOW_BACKEND_DATABASE_URI", _PG_URI)
    monkeypatch.delenv("M8FLOW_DATABASE_URI", raising=False)
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATION_PATH.parents[1]))
    return cfg


def _index_state(engine, schema: str = "public") -> bool | None:
    """indisvalid of the run-stats index in `schema`; None when absent."""
    with engine.connect() as connection:
        return connection.execute(
            sa.text(
                "SELECT i.indisvalid FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relname = :name AND n.nspname = :schema"
            ),
            {"name": _INDEX, "schema": schema},
        ).scalar()


def _ddl_seen(call) -> list[str]:
    seen: list[str] = []

    def _before(_conn, _cursor, statement, _parameters, _context, _executemany):
        if _INDEX in statement and statement.lstrip().upper().startswith(("CREATE", "DROP")):
            seen.append(" ".join(statement.split()))

    sa.event.listen(sa.engine.Engine, "before_cursor_execute", _before)
    try:
        call()
    finally:
        sa.event.remove(sa.engine.Engine, "before_cursor_execute", _before)
    return seen


@_needs_postgres
def test_postgres_builds_and_drops_concurrently_and_is_idempotent(monkeypatch):
    cfg = _alembic(monkeypatch)
    engine = sa.create_engine(_PG_URI)
    command.upgrade(cfg, "head")

    dropped = _ddl_seen(lambda: command.downgrade(cfg, _PREVIOUS))
    assert _index_state(engine) is None
    command.stamp(cfg, _HEAD)
    command.downgrade(cfg, _PREVIOUS)  # index already gone: the guard makes this a no-op
    created = _ddl_seen(lambda: command.upgrade(cfg, "head"))
    again = _ddl_seen(lambda: command.upgrade(cfg, "head"))

    assert dropped == [f"DROP INDEX CONCURRENTLY {_INDEX}"]
    assert [sql.split(" ON ")[0] for sql in created] == [f"CREATE INDEX CONCURRENTLY {_INDEX}"]
    assert again == []
    assert _index_state(engine) is True


@_needs_postgres
def test_postgres_rebuilds_an_invalid_index(monkeypatch):
    """An interrupted CONCURRENTLY build leaves an INVALID index; upgrade replaces it."""
    cfg = _alembic(monkeypatch)
    engine = sa.create_engine(_PG_URI)
    command.upgrade(cfg, "head")
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE pg_index SET indisvalid = false WHERE indexrelid = to_regclass(:name)"),
            {"name": _INDEX},
        )
    command.stamp(cfg, _PREVIOUS)
    assert _index_state(engine) is False

    command.upgrade(cfg, "head")

    assert _index_state(engine) is True


@_needs_postgres
def test_postgres_validity_check_ignores_a_same_named_index_in_another_schema(monkeypatch):
    """PR review: the validity lookup must be scoped to this schema's process_instance."""
    cfg = _alembic(monkeypatch)
    engine = sa.create_engine(_PG_URI)
    command.upgrade(cfg, "head")
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA IF EXISTS run_stats_decoy CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA run_stats_decoy"))
        connection.execute(sa.text("CREATE TABLE run_stats_decoy.process_instance (m8f_tenant_id text)"))
        connection.execute(sa.text(f"CREATE INDEX {_INDEX} ON run_stats_decoy.process_instance (m8f_tenant_id)"))
        connection.execute(
            sa.text("UPDATE pg_index SET indisvalid = false WHERE indexrelid = to_regclass(:name)"),
            {"name": f"run_stats_decoy.{_INDEX}"},
        )
    try:
        command.downgrade(cfg, _PREVIOUS)
        assert _index_state(engine) is None

        command.upgrade(cfg, "head")

        assert _index_state(engine) is True
        assert _index_state(engine, schema="run_stats_decoy") is False  # left alone
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA IF EXISTS run_stats_decoy CASCADE"))
