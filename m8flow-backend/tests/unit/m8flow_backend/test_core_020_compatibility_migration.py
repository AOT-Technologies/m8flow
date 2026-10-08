"""Safety regressions for the consolidated core 0.2.0 migration."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "b2c3d4e5f6a7_upgrade_core_0_2_0_compatibility.py"
)
_HOST_TIMESTAMP_CLEANUP_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "c3d4e5f6a7b8_remove_host_epoch_timestamp_columns.py"
)
_CORE_EPOCH_REMOVAL_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "d4e5f6a7b8c9_remove_core_epoch_timestamp_columns.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("core_012_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _host_timestamp_cleanup_module():
    spec = importlib.util.spec_from_file_location(
        "host_timestamp_cleanup_migration", _HOST_TIMESTAMP_CLEANUP_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _core_epoch_removal_module():
    spec = importlib.util.spec_from_file_location(
        "core_epoch_removal_migration", _CORE_EPOCH_REMOVAL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration_function(connection, function) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        function()


def _create_json_legacy_schema(connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "m8flow_tenant",
        metadata,
        sa.Column("id", sa.String(255), primary_key=True),
    )
    sa.Table(
        "json_data",
        metadata,
        sa.Column("hash", sa.String(255), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    sa.Table(
        "bpmn_process",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=True),
        sa.Column("json_data_hash", sa.String(255), nullable=True),
    )
    sa.Table(
        "task",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=True),
        sa.Column("json_data_hash", sa.String(255), nullable=True),
        sa.Column("python_env_data_hash", sa.String(255), nullable=True),
    )
    metadata.create_all(connection)


def test_json_migration_deduplicates_repeated_references_across_all_sources():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _create_json_legacy_schema(connection)
        connection.execute(sa.text("INSERT INTO m8flow_tenant (id) VALUES ('tenant-a'), ('tenant-b')"))
        connection.execute(
            sa.text("INSERT INTO json_data (hash, data) VALUES ('shared', '{\"value\": 1}')")
        )
        connection.execute(
            sa.text(
                "INSERT INTO bpmn_process (id, m8f_tenant_id, json_data_hash) "
                "VALUES (1, 'tenant-a', 'shared'), (2, 'tenant-b', 'shared'), "
                "(3, ' tenant-a ', 'shared')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO task (id, m8f_tenant_id, json_data_hash, python_env_data_hash) "
                "VALUES (1, 'tenant-a', 'shared', 'shared'), (2, 'tenant-a', NULL, NULL)"
            )
        )

        _run_migration_function(connection, migration._tenant_scope_json_data)

        rows = connection.execute(
            sa.text("SELECT m8f_tenant_id, hash, data FROM json_data ORDER BY m8f_tenant_id")
        ).all()
        assert [(row[0], row[1]) for row in rows] == [
            ("tenant-a", "shared"),
            ("tenant-b", "shared"),
        ]
        assert all(
            (
                json.loads(json.loads(row[2]))
                if isinstance(row[2], str)
                else row[2]
            )
            == {"value": 1}
            for row in rows
        )


def test_timestamp_migration_upgrades_host_owned_tables():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = sa.MetaData()
        secret = sa.Table(
            "secret",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
            sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        )
        metadata.create_all(connection)
        connection.execute(
            secret.insert().values(
                id=1,
                created_at_in_seconds=2_208_988_800,
                updated_at_in_seconds=2_208_988_801,
            )
        )

        _run_migration_function(connection, migration._add_timestamp_columns)

        columns = {column["name"]: column["type"] for column in sa.inspect(connection).get_columns("secret")}
        assert {"created_at", "updated_at"} <= columns.keys()
        assert columns["created_at_in_seconds"].__class__.__name__.lower() in {"bigint", "biginteger"}
        row = connection.execute(
            sa.text("SELECT created_at, updated_at FROM secret WHERE id = 1")
        ).one()
        assert str(row.created_at).startswith("2040-01-01")
        assert str(row.updated_at).startswith("2040-01-01")


def test_timestamp_migration_backfills_both_nats_key_audit_timestamps():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = sa.MetaData()
        nats_key = sa.Table(
            "m8flow_nats_api_key",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at_in_seconds", sa.Integer(), nullable=True),
            sa.Column("updated_at_in_seconds", sa.Integer(), nullable=True),
        )
        metadata.create_all(connection)
        connection.execute(
            nats_key.insert().values(
                id=1,
                created_at_in_seconds=2_208_988_800,
                updated_at_in_seconds=2_208_988_801,
            )
        )

        _run_migration_function(connection, migration._add_timestamp_columns)

        row = connection.execute(
            sa.text(
                "SELECT created_at, updated_at FROM m8flow_nats_api_key WHERE id = 1"
            )
        ).one()
        assert str(row.created_at).startswith("2040-01-01")
        assert str(row.updated_at).startswith("2040-01-01")


@pytest.mark.parametrize("dialect", ["mysql", "mariadb"])
def test_timestamp_migration_supports_mysql_family_dialects(dialect):
    migration = _migration_module()

    assert migration._epoch_to_datetime_expression(dialect, "created_at_in_seconds") == (
        "FROM_UNIXTIME(created_at_in_seconds)"
    )


def test_host_timestamp_cleanup_drops_only_host_epoch_columns():
    migration = _host_timestamp_cleanup_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = sa.MetaData()
        sa.Table(
            "secret",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at_in_seconds", sa.Integer()),
            sa.Column("updated_at_in_seconds", sa.Integer()),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )
        sa.Table(
            "m8flow_connector_configuration",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at_in_seconds", sa.Integer()),
            sa.Column("updated_at_in_seconds", sa.Integer()),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )
        # Core-owned tables are intentionally outside this migration.
        sa.Table(
            "bpmn_process",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("start_in_seconds", sa.Integer()),
            sa.Column("started_at", sa.DateTime(timezone=True)),
        )
        metadata.create_all(connection)
        connection.execute(
            sa.text(
                "INSERT INTO secret (id, created_at_in_seconds, updated_at_in_seconds, created_at, updated_at) "
                "VALUES (1, 10, 11, '2040-01-01 00:00:00', '2040-01-01 00:00:01')"
            )
        )

        _run_migration_function(connection, migration.upgrade)

        secret_columns = {column["name"] for column in sa.inspect(connection).get_columns("secret")}
        connector_columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("m8flow_connector_configuration")
        }
        core_columns = {column["name"] for column in sa.inspect(connection).get_columns("bpmn_process")}
        assert {"created_at_in_seconds", "updated_at_in_seconds"}.isdisjoint(secret_columns)
        assert {"created_at_in_seconds", "updated_at_in_seconds"}.isdisjoint(connector_columns)
        assert "start_in_seconds" in core_columns
        assert connection.execute(sa.text("SELECT created_at, updated_at FROM secret WHERE id = 1")).one() == (
            "2040-01-01 00:00:00",
            "2040-01-01 00:00:01",
        )


def test_host_timestamp_cleanup_repairs_missing_native_columns_before_drop():
    migration = _host_timestamp_cleanup_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = sa.MetaData()
        sa.Table(
            "secret",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at_in_seconds", sa.Integer()),
        )
        metadata.create_all(connection)
        connection.execute(
            sa.text(
                "INSERT INTO secret (id, created_at_in_seconds) VALUES (1, 2208988800)"
            )
        )

        _run_migration_function(connection, migration.upgrade)

        columns = {column["name"] for column in sa.inspect(connection).get_columns("secret")}
        assert "created_at_in_seconds" not in columns
        assert "created_at" in columns
        value = connection.execute(sa.text("SELECT created_at FROM secret WHERE id = 1")).scalar_one()
        assert str(value).startswith("2040-01-01")


@pytest.mark.parametrize(
    ("reference_tenant", "expected_message"),
    [
        ("missing-tenant", "referenced tenants are missing"),
        (None, "null tenant or payload reference"),
    ],
)
def test_json_migration_aborts_before_rekeying_invalid_references(reference_tenant, expected_message):
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _create_json_legacy_schema(connection)
        connection.execute(sa.text("INSERT INTO json_data (hash, data) VALUES ('shared', '{\"value\": 1}')"))
        if reference_tenant == "missing-tenant":
            tenant_sql = ":tenant"
            params = {"tenant": reference_tenant}
        else:
            tenant_sql = "NULL"
            params = {}
        connection.execute(
            sa.text(
                "INSERT INTO bpmn_process (id, m8f_tenant_id, json_data_hash) "
                f"VALUES (1, {tenant_sql}, 'shared')"
            ),
            params,
        )

        with pytest.raises(RuntimeError, match=expected_message):
            _run_migration_function(connection, migration._tenant_scope_json_data)

        assert {column["name"] for column in sa.inspect(connection).get_columns("json_data")} == {
            "hash",
            "data",
        }
        assert connection.execute(sa.text("SELECT hash FROM json_data")).scalars().all() == ["shared"]
        assert "m8f_json_data_tenant_scope_stage" not in sa.inspect(connection).get_table_names()


@pytest.mark.parametrize(
    ("setup_sql", "expected_message"),
    [
        (
            "INSERT INTO bpmn_process (id, m8f_tenant_id, json_data_hash) "
            "VALUES (1, 'tenant-a', 'missing')",
            "referenced payload hashes are missing",
        ),
    ],
)
def test_json_migration_aborts_on_unresolvable_payloads(setup_sql, expected_message):
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _create_json_legacy_schema(connection)
        connection.execute(sa.text("INSERT INTO m8flow_tenant (id) VALUES ('tenant-a')"))
        connection.execute(sa.text(setup_sql))

        with pytest.raises(RuntimeError, match=expected_message):
            _run_migration_function(connection, migration._tenant_scope_json_data)

        assert {column["name"] for column in sa.inspect(connection).get_columns("json_data")} == {
            "hash",
            "data",
        }
        assert "m8f_json_data_tenant_scope_stage" not in sa.inspect(connection).get_table_names()


def test_json_migration_drops_unreferenced_payloads_and_rekeys_the_rest():
    # Orphans are left behind by deleted tasks/instances; nothing can read them and
    # they have no tenant to scope to (dev had to be cleaned by hand; QA/demo have them too).
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _create_json_legacy_schema(connection)
        connection.execute(sa.text("INSERT INTO m8flow_tenant (id) VALUES ('tenant-a')"))
        connection.execute(
            sa.text(
                "INSERT INTO json_data (hash, data) VALUES "
                "('kept', '{\"value\": 1}'), ('orphan-1', '{}'), ('orphan-2', '{}')"
            )
        )
        connection.execute(
            sa.text("INSERT INTO task (id, m8f_tenant_id, json_data_hash) VALUES (1, 'tenant-a', 'kept')")
        )

        _run_migration_function(connection, migration._tenant_scope_json_data)

        assert connection.execute(sa.text("SELECT m8f_tenant_id, hash FROM json_data")).all() == [
            ("tenant-a", "kept")
        ]


def test_json_migration_handles_a_table_of_only_orphans():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _create_json_legacy_schema(connection)
        connection.execute(sa.text("INSERT INTO json_data (hash, data) VALUES ('orphan', '{}')"))

        _run_migration_function(connection, migration._tenant_scope_json_data)

        assert "m8f_tenant_id" in {column["name"] for column in sa.inspect(connection).get_columns("json_data")}
        assert connection.execute(sa.text("SELECT COUNT(*) FROM json_data")).scalar_one() == 0


def test_work_item_and_authorization_backfills_preserve_existing_rows(monkeypatch):
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = sa.MetaData()
        sa.Table("m8flow_tenant", metadata, sa.Column("id", sa.String(255), primary_key=True))
        sa.Table("process_instance", metadata, sa.Column("id", sa.Integer(), primary_key=True))
        sa.Table("task", metadata, sa.Column("guid", sa.String(36), primary_key=True))
        sa.Table(
            "group",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("identifier", sa.String(255)),
        )
        sa.Table("user", metadata, sa.Column("id", sa.Integer(), primary_key=True))
        sa.Table(
            "human_task",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("process_instance_id", sa.Integer(), nullable=False),
            sa.Column("task_guid", sa.String(36)),
            sa.Column("task_id", sa.String(50)),
            sa.Column("lane_assignment_id", sa.Integer()),
            sa.Column("completed_by_user_id", sa.Integer()),
            sa.Column("actual_owner_id", sa.Integer()),
            sa.Column("task_status", sa.String(50), nullable=False),
            sa.Column("completed", sa.Boolean(), nullable=False),
            sa.Column("updated_at_in_seconds", sa.BigInteger()),
            sa.Column("created_at_in_seconds", sa.BigInteger()),
            sa.Column("updated_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
        )
        sa.Table(
            "permission_target",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("uri", sa.String(255), nullable=False),
            sa.Column("command", sa.String(20)),
        )
        sa.Table(
            "principal",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer()),
            sa.Column("group_id", sa.Integer()),
        )
        metadata.create_all(connection)
        connection.execute(sa.text("INSERT INTO m8flow_tenant (id) VALUES ('tenant-a')"))
        connection.execute(sa.text("INSERT INTO process_instance (id) VALUES (1)"))
        connection.execute(sa.text("INSERT INTO task (guid) VALUES ('task-guid')"))
        connection.execute(sa.text("INSERT INTO \"group\" (id) VALUES (7)"))
        connection.execute(sa.text("INSERT INTO \"user\" (id) VALUES (9)"))
        connection.execute(
            sa.text(
                "INSERT INTO human_task (id, process_instance_id, task_guid, task_id, "
                "lane_assignment_id, completed_by_user_id, actual_owner_id, task_status, "
                "completed, m8f_tenant_id) VALUES "
                "(4, 1, 'task-guid', 'Activity_1', 7, 9, NULL, 'READY', 0, 'tenant-a')"
            )
        )
        connection.execute(
            sa.text("INSERT INTO permission_target (id, uri, command) VALUES (3, '/processes', 'GET')")
        )
        connection.execute(sa.text("INSERT INTO \"group\" (id, identifier) VALUES (8, 'Submitters')"))

        batch_tables: list[str] = []
        original_batch_alter_table = migration.op.batch_alter_table

        def tracked_batch_alter_table(table_name, *args, **kwargs):
            batch_tables.append(table_name)
            return original_batch_alter_table(table_name, *args, **kwargs)

        monkeypatch.setattr(migration.op, "batch_alter_table", tracked_batch_alter_table)

        _run_migration_function(connection, migration._create_work_item)
        _run_migration_function(connection, migration._authorization_schema)

        assert batch_tables.count("group") == 1
        assert batch_tables.count("permission_target") == 1
        assert batch_tables.count("principal") == 1

        work_item = connection.execute(
            sa.text("SELECT id, process_instance_id, task_guid, m8f_tenant_id FROM work_item")
        ).one()
        assert tuple(work_item) == (4, 1, "task-guid", "tenant-a")
        assert connection.execute(
            sa.text("SELECT authorization_key FROM \"group\" WHERE id = 8")
        ).scalar_one() == "authorization:Submitters"
        target = connection.execute(
            sa.text("SELECT uri, command, resource_type, resource_id FROM permission_target")
        ).one()
        assert tuple(target) == ("/processes", "GET", None, None)


def test_authorization_backfill_namespaces_lane_group_keys():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = sa.MetaData()
        sa.Table(
            "group",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("identifier", sa.String(255)),
            sa.Column("source_is_open_id", sa.Boolean(), nullable=False),
        )
        metadata.create_all(connection)
        connection.execute(
            sa.text(
                'INSERT INTO "group" (id, identifier, source_is_open_id) VALUES '
                "(7, 'tenant-a:Submitters', 0), (8, 'tenant-a:Submitters', 1)"
            )
        )

        _run_migration_function(connection, migration._authorization_schema)

        rows = connection.execute(
            sa.text('SELECT id, authorization_key FROM "group" ORDER BY id')
        ).all()
        assert rows == [
            (7, "authorization:lane:7"),
            (8, "authorization:tenant-a:Submitters"),
        ]


def test_authorization_backfill_still_rejects_duplicate_rbac_identifiers():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = sa.MetaData()
        sa.Table(
            "group",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("identifier", sa.String(255)),
            sa.Column("source_is_open_id", sa.Boolean(), nullable=False),
        )
        metadata.create_all(connection)
        connection.execute(
            sa.text(
                'INSERT INTO "group" (id, identifier, source_is_open_id) VALUES '
                "(7, 'tenant-a:Submitters', 1), (8, 'tenant-a:Submitters', 1)"
            )
        )

        with pytest.raises(RuntimeError, match="duplicate RBAC group identifiers"):
            _run_migration_function(connection, migration._authorization_schema)


def test_core_epoch_removal_is_reversible_and_leaves_native_columns_intact():
    migration = _core_epoch_removal_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata = sa.MetaData()
        sa.Table(
            "process_instance",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("start_in_seconds", sa.BigInteger()),
            sa.Column("end_in_seconds", sa.BigInteger()),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("ended_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )
        sa.Index("ix_process_instance_start_in_seconds", "start_in_seconds")
        sa.Table(
            "process_instance_event",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("timestamp", sa.Numeric(17, 6)),
            sa.Column("occurred_at", sa.DateTime(timezone=True)),
        )
        metadata.create_all(connection)
        connection.execute(
            sa.text(
                "INSERT INTO process_instance "
                "(id, start_in_seconds, end_in_seconds, started_at, ended_at, updated_at) "
                "VALUES (1, 10, 20, '2040-01-01 00:00:00', '2040-01-01 00:01:00', "
                "'2040-01-01 00:01:00')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO process_instance_event (id, timestamp, occurred_at) "
                "VALUES (1, 10.5, '2040-01-01 00:00:10.500000')"
            )
        )

        _run_migration_function(connection, migration.upgrade)

        process_columns = {column["name"] for column in sa.inspect(connection).get_columns("process_instance")}
        event_columns = {column["name"] for column in sa.inspect(connection).get_columns("process_instance_event")}
        assert "start_in_seconds" not in process_columns
        assert "end_in_seconds" not in process_columns
        assert {"started_at", "ended_at", "updated_at"}.issubset(process_columns)
        assert "timestamp" not in event_columns
        assert "occurred_at" in event_columns
        assert connection.execute(sa.text("SELECT started_at FROM process_instance WHERE id = 1")).scalar_one() is not None

        _run_migration_function(connection, migration.downgrade)
        process_columns = {column["name"] for column in sa.inspect(connection).get_columns("process_instance")}
        event_columns = {column["name"] for column in sa.inspect(connection).get_columns("process_instance_event")}
        assert {"start_in_seconds", "end_in_seconds"}.issubset(process_columns)
        assert "timestamp" in event_columns
        assert connection.execute(sa.text("SELECT start_in_seconds FROM process_instance WHERE id = 1")).scalar_one() is None
