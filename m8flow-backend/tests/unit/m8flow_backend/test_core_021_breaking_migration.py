"""Regression tests for the core 0.2.1 breaking migration DML."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.dialects import mysql, postgresql, sqlite


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


def test_process_digest_migration_rejects_collisions_and_alias_mismatches():
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
            [
                {
                    "id": 1,
                    "m8f_tenant_id": "tenant-a",
                    "full_process_model_hash": "digest-a",
                    "single_process_hash": "digest-a",
                },
                {
                    "id": 2,
                    "m8f_tenant_id": "tenant-a",
                    "full_process_model_hash": "digest-a",
                    "single_process_hash": "digest-a",
                },
            ],
        )
        with pytest.raises(RuntimeError, match="Canonical process digest collisions"):
            _run_migration_function(connection, migration._validate_process_digests)

        connection.execute(
            process_definition.update()
            .where(process_definition.c.id == 2)
            .values(full_process_model_hash="digest-b", single_process_hash="digest-c")
        )
        with pytest.raises(RuntimeError, match="Process digest aliases disagree"):
            _run_migration_function(connection, migration._validate_process_digests)


def test_process_digest_migration_rejects_null_canonical_digest():
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
                "full_process_model_hash": None,
                "single_process_hash": None,
            },
        )
        _run_migration_function(connection, migration._validate_process_digests)
        with pytest.raises(RuntimeError, match="missing canonical digests"):
            _run_migration_function(connection, migration._migrate_process_digests)


def test_human_task_assignments_copy_is_unique_and_tenant_scoped():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    work_item = sa.Table(
        "work_item",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
    )
    human_task_user = sa.Table(
        "human_task_user",
        metadata,
        sa.Column("human_task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("added_by", sa.String(20)),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(work_item.insert(), [{"id": 10}, {"id": 20}])
        connection.execute(
            human_task_user.insert(),
            [
                # Duplicate legacy rows must not violate the destination PK.
                {
                    "human_task_id": 10,
                    "user_id": 7,
                    "added_by": "system",
                    "m8f_tenant_id": "tenant-a",
                },
                {
                    "human_task_id": 10,
                    "user_id": 7,
                    "added_by": "system",
                    "m8f_tenant_id": "tenant-a",
                },
                {
                    "human_task_id": 20,
                    "user_id": 7,
                    "added_by": "user",
                    "m8f_tenant_id": "tenant-b",
                },
            ],
        )

        _run_migration_function(connection, migration._migrate_assignments)
        _run_migration_function(connection, migration._migrate_assignments)

        rows = connection.execute(
            sa.text(
                "SELECT work_item_id, user_id, added_by, m8f_tenant_id "
                "FROM work_item_user ORDER BY work_item_id"
            )
        ).all()

    assert rows == [
        (10, 7, "system", "tenant-a"),
        (20, 7, "user", "tenant-b"),
    ]


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


@pytest.mark.parametrize(
    ("dialect_name", "dialect", "expected_function"),
    [
        ("sqlite", sqlite.dialect(), "datetime"),
        ("postgresql", postgresql.dialect(), "to_timestamp"),
        ("mysql", mysql.dialect(), "from_unixtime"),
        ("mariadb", mysql.dialect(), "from_unixtime"),
    ],
)
def test_event_timestamp_expression_supports_all_migration_dialects(
    dialect_name, dialect, expected_function
):
    migration = _migration_module()
    event = sa.table("process_instance_event", sa.column("timestamp"))

    expression = migration._event_timestamp_expression(dialect_name, event)

    assert expected_function in str(expression.compile(dialect=dialect)).lower()


def test_event_migration_rejects_unknown_event_types():
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
            {"id": 1, "event_type": "unexpected_event", "timestamp": 1},
        )
        with pytest.raises(RuntimeError, match="cannot be assigned a category"):
            _run_migration_function(connection, migration._migrate_events)
