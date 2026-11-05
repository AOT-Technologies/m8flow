"""Database-level idempotency for task completion audit events."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import pytest


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "d1e2f3a4b5c6_unique_task_completion_events.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("unique_task_completion_events", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema(engine):
    metadata = sa.MetaData()
    sa.Table(
        "process_instance_event",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
        sa.Column("process_instance_id", sa.Integer, nullable=False),
        sa.Column("task_guid", sa.String(36)),
        sa.Column("event_type", sa.String(50), nullable=False),
    )
    metadata.create_all(engine)


def _apply(connection, migration, operation):
    with Operations.context(MigrationContext.configure(connection)):
        getattr(migration, operation)()


def test_table_existence_guard_uses_public_inspector_table_names_api():
    migration = _migration_module()

    class InspectorWithoutHasTable:
        def get_table_names(self):
            return ["process_instance_event"]

    assert migration._table_exists(InspectorWithoutHasTable()) is True

    class MissingTableInspector:
        def get_table_names(self):
            return []

    assert migration._table_exists(MissingTableInspector()) is False


def test_unique_index_blocks_duplicate_task_completed_but_allows_other_events():
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    migration = _migration_module()

    with engine.begin() as connection:
        events = sa.Table("process_instance_event", sa.MetaData(), autoload_with=connection)
        connection.execute(
            events.insert(),
            [
                {"m8f_tenant_id": "t1", "process_instance_id": 1, "task_guid": "g1", "event_type": "task_completed"},
                {"m8f_tenant_id": "t1", "process_instance_id": 1, "task_guid": "g1", "event_type": "task_failed"},
                {"m8f_tenant_id": "t1", "process_instance_id": 1, "task_guid": None, "event_type": "task_completed"},
            ],
        )
        _apply(connection, migration, "upgrade")

        with pytest.raises(sa.exc.IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    events.insert().values(
                        m8f_tenant_id="t1",
                        process_instance_id=1,
                        task_guid="g1",
                        event_type="task_completed",
                    )
                )

        connection.execute(
            events.insert().values(
                m8f_tenant_id="t1",
                process_instance_id=2,
                task_guid="g1",
                event_type="task_completed",
            )
        )
        assert connection.scalar(sa.select(sa.func.count()).select_from(events)) == 4

        _apply(connection, migration, "downgrade")


def test_upgrade_is_noop_when_unique_index_already_exists(monkeypatch):
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    migration = _migration_module()

    with engine.begin() as connection:
        events = sa.Table("process_instance_event", sa.MetaData(), autoload_with=connection)
        connection.execute(
            events.insert(),
            [
                {"m8f_tenant_id": "t1", "process_instance_id": 1, "task_guid": "g1", "event_type": "task_completed"},
            ],
        )
        sa.Index(
            migration.INDEX_NAME,
            events.c.m8f_tenant_id,
            events.c.process_instance_id,
            events.c.task_guid,
            unique=True,
            sqlite_where=sa.and_(
                events.c.event_type == "task_completed",
                events.c.task_guid.is_not(None),
            ),
        ).create(connection)

        def unexpected_duplicate_query(*_args, **_kwargs):
            raise AssertionError("upgrade should return before checking existing duplicates")

        monkeypatch.setattr(migration.sa, "text", unexpected_duplicate_query)
        _apply(connection, migration, "upgrade")

        assert migration.INDEX_NAME in {
            item["name"] for item in sa.inspect(connection).get_indexes("process_instance_event")
        }
        assert connection.scalar(sa.select(sa.func.count()).select_from(events)) == 1


def test_migration_refuses_existing_duplicates_without_deleting_audit_rows():
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    migration = _migration_module()

    with engine.begin() as connection:
        events = sa.Table("process_instance_event", sa.MetaData(), autoload_with=connection)
        connection.execute(
            events.insert(),
            [
                {"m8f_tenant_id": "t1", "process_instance_id": 1, "task_guid": "g1", "event_type": "task_completed"},
                {"m8f_tenant_id": "t1", "process_instance_id": 1, "task_guid": "g1", "event_type": "task_completed"},
            ],
        )

        try:
            _apply(connection, migration, "upgrade")
        except RuntimeError as exc:
            assert "existing duplicates" in str(exc)
            assert "tenant='t1'" in str(exc)
        else:
            raise AssertionError("migration should reject ambiguous historical duplicates")

        assert connection.scalar(sa.select(sa.func.count()).select_from(events)) == 2
        assert migration.INDEX_NAME not in {
            item["name"] for item in sa.inspect(connection).get_indexes("process_instance_event")
        }
