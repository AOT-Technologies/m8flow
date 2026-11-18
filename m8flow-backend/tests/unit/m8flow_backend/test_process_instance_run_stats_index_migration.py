"""M8F-703: composite index for the Processes page run stats."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
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
