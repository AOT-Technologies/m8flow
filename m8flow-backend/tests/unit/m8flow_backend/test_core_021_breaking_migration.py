"""Regression tests for the core 0.2.1 breaking migration DML."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
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


def test_downgrade_rejects_both_group_table_names(tmp_path):
    migration = _migration_module()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'ambiguous-group-tables.db'}")
    metadata = sa.MetaData()
    sa.Table("group", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("m8f_group", metadata, sa.Column("id", sa.Integer, primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        with pytest.raises(RuntimeError, match="both m8f_group and group exist"):
            _run_migration_function(connection, migration.downgrade)


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
                "full_process_model_hash": "xml-digest-a",
                "single_process_hash": "process-digest-a",
            },
        )
        _run_migration_function(connection, migration._validate_process_digests)
        _run_migration_function(connection, migration._migrate_process_digests)

        row = connection.execute(
            sa.text(
                "SELECT process_xml_digest FROM bpmn_process_definition WHERE id = 1"
            )
        ).scalar_one()

    assert row == "xml-digest-a"
    columns = {column["name"] for column in sa.inspect(engine).get_columns("bpmn_process_definition")}
    assert "process_xml_digest" in columns
    assert "full_process_model_hash" not in columns
    assert "single_process_hash" not in columns


def test_process_digest_migration_rejects_collisions_but_allows_distinct_legacy_hashes():
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


def test_work_item_migration_copies_human_task_rows():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    human_task = sa.Table(
        "human_task",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_instance_id", sa.Integer(), nullable=False),
        sa.Column("task_guid", sa.String(36)),
        sa.Column("lane_assignment_id", sa.Integer()),
        sa.Column("completed_by_user_id", sa.Integer()),
        sa.Column("actual_owner_id", sa.Integer()),
        sa.Column("task_status", sa.String(50), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
    )
    sa.Table("m8f_group", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            human_task.insert(),
            [
                {
                    "id": 10,
                    "process_instance_id": 100,
                    "task_guid": "task-a",
                    "task_status": "READY",
                    "completed": False,
                    "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                    "updated_at": datetime(2025, 1, 2, tzinfo=timezone.utc),
                    "m8f_tenant_id": "tenant-a",
                },
                {
                    "id": 20,
                    "process_instance_id": 200,
                    "task_guid": "task-b",
                    "task_status": "COMPLETED",
                    "completed": True,
                    "created_at": datetime(2025, 2, 1, tzinfo=timezone.utc),
                    "updated_at": datetime(2025, 2, 2, tzinfo=timezone.utc),
                    "m8f_tenant_id": "tenant-b",
                },
            ],
        )

        _run_migration_function(connection, migration._migrate_work_items)

        rows = connection.execute(
            sa.text(
                "SELECT id, process_instance_id, task_guid, task_status, completed, m8f_tenant_id "
                "FROM work_item ORDER BY id"
            )
        ).all()

    assert rows == [
        (10, 100, "task-a", "READY", 0, "tenant-a"),
        (20, 200, "task-b", "COMPLETED", 1, "tenant-b"),
    ]
    inspector = sa.inspect(engine)
    constraints = inspector.get_unique_constraints("work_item")
    assert {constraint["name"] for constraint in constraints} == {
        "m8f_work_item_task_guid_key"
    }
    foreign_keys = inspector.get_foreign_keys("work_item")
    assert {foreign_key["name"] for foreign_key in foreign_keys} == {
        "fk_work_item_process_instance_id_process_instance",
        "fk_work_item_task_guid_task",
        "fk_work_item_lane_assignment_id_m8f_group",
        "fk_work_item_completed_by_user_id_user",
        "fk_work_item_actual_owner_id_user",
        "fk_work_item_m8f_tenant_id_m8flow_tenant",
    }
    assert {index["name"] for index in inspector.get_indexes("work_item")} == {
        "ix_work_item_process_instance_id",
        "ix_work_item_task_guid",
        "ix_work_item_lane_assignment_id",
        "ix_work_item_completed_by_user_id",
        "ix_work_item_actual_owner_id",
        "ix_work_item_m8f_tenant_id",
        "ix_work_item_completed",
    }


def test_work_item_migration_requires_group_table_before_creating_fk():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("human_task", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        with pytest.raises(
            RuntimeError,
            match="neither m8f_group nor group exists",
        ):
            _run_migration_function(connection, migration._migrate_work_items)


def test_work_item_migration_rejects_stale_existing_backfill_before_cleanup():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()

    def columns():
        return [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("process_instance_id", sa.Integer(), nullable=False),
            sa.Column("task_guid", sa.String(36)),
            sa.Column("lane_assignment_id", sa.Integer()),
            sa.Column("completed_by_user_id", sa.Integer()),
            sa.Column("actual_owner_id", sa.Integer()),
            sa.Column("task_status", sa.String(50), nullable=False),
            sa.Column("completed", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
        ]

    human_task = sa.Table("human_task", metadata, *columns())
    work_item = sa.Table("work_item", metadata, *columns())
    metadata.create_all(engine)

    row = {
        "id": 10,
        "process_instance_id": 100,
        "task_guid": "task-a",
        "task_status": "READY",
        "completed": False,
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 1, 2, tzinfo=timezone.utc),
        "m8f_tenant_id": "tenant-a",
    }
    with engine.begin() as connection:
        connection.execute(human_task.insert(), row)
        stale_row = dict(row, task_status="COMPLETED")
        connection.execute(work_item.insert(), stale_row)

        with pytest.raises(RuntimeError, match="rows differ for approval-chain fields"):
            _run_migration_function(connection, migration._migrate_work_items)

        assert connection.execute(sa.select(sa.func.count()).select_from(human_task)).scalar_one() == 1


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
    inspector = sa.inspect(engine)
    assert {foreign_key["name"] for foreign_key in inspector.get_foreign_keys("work_item_user")} == {
        "fk_work_item_user_work_item_id_work_item",
        "fk_work_item_user_user_id_user",
        "fk_work_item_user_m8f_tenant_id_m8flow_tenant",
    }
    assert {index["name"] for index in inspector.get_indexes("work_item_user")} == {
        "ix_work_item_user_added_by",
        "ix_work_item_user_user_id",
        "ix_work_item_user_m8f_tenant_id",
    }


def test_human_task_assignments_reject_conflicting_destination_pk_metadata():
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
        connection.execute(work_item.insert(), {"id": 10})
        connection.execute(
            human_task_user.insert(),
            [
                {
                    "human_task_id": 10,
                    "user_id": 7,
                    "added_by": "system",
                    "m8f_tenant_id": "tenant-a",
                },
                {
                    "human_task_id": 10,
                    "user_id": 7,
                    "added_by": "user",
                    "m8f_tenant_id": "tenant-a",
                },
            ],
        )

        with pytest.raises(RuntimeError, match="Conflicting human-task assignment metadata"):
            _run_migration_function(connection, migration._migrate_assignments)

        assert "work_item_user" in sa.inspect(connection).get_table_names()
        assert connection.execute(sa.text("SELECT COUNT(*) FROM work_item_user")).scalar_one() == 0


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
        (1, "1970-01-01 00:00:01.000+00:00", "process"),
        (2, "1970-01-01 00:00:02.000+00:00", "task"),
    ]
    with engine.connect() as connection:
        typed_events = sa.Table("process_instance_event", sa.MetaData(), autoload_with=connection)
        typed_rows = connection.execute(
            sa.select(typed_events.c.occurred_at).order_by(typed_events.c.id)
        ).scalars().all()
    assert [value.isoformat() for value in typed_rows] == [
        "1970-01-01T00:00:01+00:00",
        "1970-01-01T00:00:02+00:00",
    ]
    columns = {column["name"] for column in sa.inspect(engine).get_columns("process_instance_event")}
    assert "occurred_at" in columns
    assert "category" in columns
    assert "timestamp" not in columns


@pytest.mark.parametrize(
    ("dialect_name", "dialect", "expected_function"),
    [
        ("sqlite", sqlite.dialect(), "strftime"),
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
