"""Regression tests for the core 0.2.1 breaking migration DML."""

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
    / "c4d5e6f7a8b9_breaking_core_0_2_1_contract.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("core_021_breaking_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration_function(connection, function) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        function()


def test_process_digest_backfill_uses_safe_expression_dml():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    process_definition = sa.Table(
        "bpmn_process_definition",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
        sa.Column("full_process_model_hash", sa.String(255)),
        sa.Column("single_process_hash", sa.String(255)),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            process_definition.insert(),
            {
                "id": 1,
                "m8f_tenant_id": "tenant-a",
                "full_process_model_hash": "digest-a",
                "single_process_hash": "digest-a",
            },
        )
        _run_migration_function(connection, migration._validate_process_digests)
        _run_migration_function(connection, migration._migrate_process_digests)

        row = connection.execute(
            sa.text(
                "SELECT process_xml_digest FROM bpmn_process_definition WHERE id = 1"
            )
        ).scalar_one()

    assert row == "digest-a"
    columns = {column["name"] for column in sa.inspect(engine).get_columns("bpmn_process_definition")}
    assert "process_xml_digest" in columns
    assert "full_process_model_hash" not in columns
    assert "single_process_hash" not in columns


def test_event_timestamp_backfill_uses_dialect_expression_dml():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    events = sa.Table(
        "process_instance_event",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            events.insert(),
            [
                {"id": 1, "event_type": "process_instance_created", "timestamp": 1},
                {"id": 2, "event_type": "task_completed", "timestamp": 2},
            ],
        )
        _run_migration_function(connection, migration._migrate_events)

        rows = connection.execute(
            sa.text(
                "SELECT id, occurred_at, category FROM process_instance_event ORDER BY id"
            )
        ).all()

    assert rows == [
        (1, "1970-01-01 00:00:01", "process"),
        (2, "1970-01-01 00:00:02", "task"),
    ]
    columns = {column["name"] for column in sa.inspect(engine).get_columns("process_instance_event")}
    assert "occurred_at" in columns
    assert "category" in columns
    assert "timestamp" not in columns
