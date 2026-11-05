"""Database-level idempotency for task completion audit events."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.mysql import mariadb
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


def test_upgrade_is_noop_when_unique_index_already_exists():
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

        executed_sql: list[str] = []

        def capture_sql(_connection, _cursor, statement, *_args):
            executed_sql.append(statement)

        sa.event.listen(connection, "before_cursor_execute", capture_sql)
        _apply(connection, migration, "upgrade")

        assert migration.INDEX_NAME in {
            item["name"] for item in sa.inspect(connection).get_indexes("process_instance_event")
        }
        assert not any("GROUP BY" in statement.upper() for statement in executed_sql)
        assert connection.scalar(sa.select(sa.func.count()).select_from(events)) == 1


@pytest.mark.parametrize("dialect", [mysql.dialect(), mariadb.MariaDBDialect()])
def test_mysql_family_index_uses_generated_column_and_is_rerunnable(monkeypatch, dialect):
    migration = _migration_module()
    created_columns = []
    created_indexes = []

    class InspectorWithoutGeneratedColumn:
        def get_columns(self, _table_name):
            return [{"name": "task_guid"}]

    monkeypatch.setattr(migration.op, "add_column", lambda *args: created_columns.append(args))
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: created_indexes.append((args, kwargs)))

    migration._create_unique_index(dialect.name, InspectorWithoutGeneratedColumn())

    assert len(created_columns) == 1
    generated_column = created_columns[0][1]
    assert generated_column.name == migration.MYSQL_UNIQUE_COLUMN
    assert isinstance(generated_column.computed, sa.Computed)
    assert len(created_indexes) == 1
    assert created_indexes[0][0][2] == [
        "m8f_tenant_id",
        "process_instance_id",
        migration.MYSQL_UNIQUE_COLUMN,
    ]
    assert created_indexes[0][1]["unique"] is True

    class InspectorWithGeneratedColumn:
        def get_columns(self, _table_name):
            return [
                {"name": "task_guid"},
                {"name": migration.MYSQL_UNIQUE_COLUMN},
            ]

    migration._create_unique_index(dialect.name, InspectorWithGeneratedColumn())
    assert len(created_columns) == 1
    assert len(created_indexes) == 2


@pytest.mark.parametrize("dialect", [mysql.dialect(), mariadb.MariaDBDialect()])
def test_mysql_family_generated_column_index_ddl_compiles(dialect):
    migration = _migration_module()
    table = sa.Table(
        "process_instance_event",
        sa.MetaData(),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
        sa.Column("process_instance_id", sa.Integer, nullable=False),
        sa.Column("task_guid", sa.String(36)),
        migration._mysql_unique_column(),
    )
    index = sa.Index(
        migration.INDEX_NAME,
        table.c.m8f_tenant_id,
        table.c.process_instance_id,
        table.c[migration.MYSQL_UNIQUE_COLUMN],
        unique=True,
    )

    column_ddl = str(sa.schema.CreateColumn(table.c[migration.MYSQL_UNIQUE_COLUMN]).compile(dialect=dialect))
    index_ddl = str(sa.schema.CreateIndex(index).compile(dialect=dialect))

    assert "GENERATED ALWAYS AS" in column_ddl
    assert "CASE WHEN event_type = 'task_completed' THEN task_guid ELSE NULL END" in column_ddl
    assert "CREATE UNIQUE INDEX" in index_ddl
    assert migration.MYSQL_UNIQUE_COLUMN in index_ddl


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
            assert "duplicate_groups=1" in str(exc)
            assert "affected_rows=2" in str(exc)
            assert "tenant='t1'" not in str(exc)
            assert "task_guid='g1'" not in str(exc)
        else:
            raise AssertionError("migration should reject ambiguous historical duplicates")

        assert connection.scalar(sa.select(sa.func.count()).select_from(events)) == 2
        assert migration.INDEX_NAME not in {
            item["name"] for item in sa.inspect(connection).get_indexes("process_instance_event")
        }


def test_duplicate_check_treats_sql_injection_shaped_data_as_values():
    engine = sa.create_engine("sqlite://")
    _schema(engine)
    migration = _migration_module()
    hostile_tenant = "tenant' OR 1=1 --"
    hostile_task_guid = "task'); DROP TABLE process_instance_event; --"

    with engine.begin() as connection:
        events = sa.Table("process_instance_event", sa.MetaData(), autoload_with=connection)
        connection.execute(
            events.insert(),
            [
                {
                    "m8f_tenant_id": hostile_tenant,
                    "process_instance_id": 1,
                    "task_guid": hostile_task_guid,
                    "event_type": "task_completed",
                },
                {
                    "m8f_tenant_id": hostile_tenant,
                    "process_instance_id": 1,
                    "task_guid": hostile_task_guid,
                    "event_type": "task_completed",
                },
                {
                    "m8f_tenant_id": "ordinary-tenant",
                    "process_instance_id": 2,
                    "task_guid": "ordinary-task",
                    "event_type": "task_failed",
                },
            ],
        )
        executed_sql: list[str] = []

        def capture_sql(_connection, _cursor, statement, *_args):
            executed_sql.append(statement)

        sa.event.listen(connection, "before_cursor_execute", capture_sql)

        with pytest.raises(RuntimeError, match="existing duplicates") as raised:
            _apply(connection, migration, "upgrade")

        assert hostile_tenant not in str(raised.value)
        assert hostile_task_guid not in str(raised.value)
        assert "duplicate_groups=1" in str(raised.value)
        assert "affected_rows=2" in str(raised.value)
        assert all(hostile_tenant not in statement for statement in executed_sql)
        assert all(hostile_task_guid not in statement for statement in executed_sql)
        assert sa.inspect(connection).has_table("process_instance_event")
        assert connection.scalar(sa.select(sa.func.count()).select_from(events)) == 3
