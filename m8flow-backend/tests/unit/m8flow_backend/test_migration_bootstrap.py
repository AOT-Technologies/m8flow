"""The migration chain must build a complete schema from a genuinely empty DB.

This is the regression that the old incremental chain failed: its root revision
created only ``m8flow_tenant`` and the next revision assumed ~30 core tables
already existed, so ``alembic upgrade head`` died with ``NoSuchTableError`` on
every fresh database and the backend crash-looped. Nothing in CI ran
``upgrade head`` against an empty database, so it shipped. These tests close
that gap: they run the real Alembic command against an empty database and assert
the resulting schema.

The SQLite case proves the chain is self-sufficient (no missing tables). The
PostgreSQL case additionally proves row-level security and the base tenant seed
land; it is skipped unless ``M8FLOW_TEST_POSTGRES_URI`` points at an empty,
disposable database.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command, op
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

import m8flow_backend.db as backend_db
from m8flow_backend.db import alembic_target_metadata

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
_JOURNAL_TABLES = ("compensation_scope", "compensation_run", "compensation_record")
_JOURNAL_REVISION = "fa8b9c0d1e2f"
_JOURNAL_OWNERSHIP = f"m8flow_{_JOURNAL_REVISION}_journal_ownership"


def _script_head() -> str:
    """The chain's current head. Asserted against the stamp rather than a literal so
    adding an ordinary incremental revision on top of the squashed root does not read
    as the NoSuchTableError regression these tests exist to catch."""
    revisions = ScriptDirectory(str(_MIGRATIONS_DIR)).get_heads()
    assert len(revisions) == 1, f"migrations must have exactly one head, found {sorted(revisions)}"
    return revisions[0]


def _orm_table_names() -> set[str]:
    return {name for metadata in alembic_target_metadata() for name in metadata.tables}


def _alembic_config(database_uri: str, monkeypatch: pytest.MonkeyPatch) -> Config:
    # env.py resolves the URL from the environment; give it the empty DB.
    monkeypatch.setenv("M8FLOW_BACKEND_DATABASE_URI", database_uri)
    monkeypatch.delenv("M8FLOW_DATABASE_URI", raising=False)
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return cfg


def test_upgrade_head_on_empty_sqlite_builds_full_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)

    # The bug: this raised NoSuchTableError before completing.
    command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    actual = set(inspector.get_table_names())

    missing = _orm_table_names() - actual
    assert not missing, f"upgrade head left tables uncreated: {sorted(missing)}"
    correlation_column = next(
        column for column in inspector.get_columns("process_instance") if column["name"] == "collaboration_correlation_key"
    )
    assert correlation_column["nullable"] and correlation_column["type"].length == 255
    assert "ix_process_instance_collaboration_lookup" in {
        index["name"] for index in inspector.get_indexes("process_instance")
    }

    # The chain ran to completion and is stamped at its one head.
    with engine.connect() as connection:
        core_stamped = connection.execute(
            sa.text("SELECT version_num FROM m8flow_core_alembic_version")
        ).scalar()
        stamped = connection.execute(
            sa.text("SELECT version_num FROM alembic_version_m8flow")
        ).scalar()
    assert core_stamped == "k2l3m4n5o6p7"
    assert stamped == _script_head()

    # Base tenant seed lands regardless of dialect.
    with engine.connect() as connection:
        seeded = connection.execute(
            sa.text("SELECT slug FROM m8flow_tenant WHERE id = 'm8flow'")
        ).scalar()
    assert seeded == "m8flow"


def test_process_model_version_upgrade_preserves_catalog_status_and_baseline(tmp_path, monkeypatch):
    from sqlalchemy.orm import Session

    from m8flow_backend.catalog import default_bpmn_xml, versions
    from m8flow_backend.models.process_model_version import ProcessModelState

    db_path = tmp_path / "catalog.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    root = tmp_path / "catalog"
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(root))
    command.upgrade(cfg, "fbcad9e02138")
    for name, metadata in (
        ("published", '{"status":"published"}'), ("paused", '{"status":"paused"}'),
        ("draft", '{"status":"draft"}'), ("legacy", '{}'),
    ):
        folder = root / "m8flow" / "test" / name
        folder.mkdir(parents=True)
        (folder / f"{name}.bpmn").write_bytes(default_bpmn_xml(process_id=name).encode())
        (folder / "form-schema.json").write_bytes(b'{"title":"Baseline"}')
        (folder / "process_model.json").write_text(metadata, encoding="utf-8")

    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        for name in ("published", "paused", "draft", "legacy"):
            model = session.get(ProcessModelState, ("m8flow", f"test/{name}"))
            assert model.status == ("published" if name == "legacy" else name)
            entries = versions.model_releases(session, model)
            if name == "draft":
                assert entries == []
                assert versions.draft_number(session, model) == 1
            else:
                entry, = entries
                assert entry.version == 1
                assert versions.read_file(entry.contents, "form-schema.json") == b'{"title":"Baseline"}'


def test_process_model_version_upgrade_rolls_back_after_later_tenant_import_fails(tmp_path, monkeypatch):
    from sqlalchemy.orm import Session

    from m8flow_backend.catalog import default_bpmn_xml, versions
    from m8flow_backend.identity import ensure_tenant
    from m8flow_backend.models.process_model_version import (
        ProcessInstanceCalledReleases,
        ProcessModelRelease,
        ProcessModelState,
    )
    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_core.models.scheduler_job import SchedulerJobModel

    database_uri = f"sqlite:///{tmp_path / 'catalog-retry.db'}"
    cfg = _alembic_config(database_uri, monkeypatch)
    root = tmp_path / "catalog"
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(root))
    previous_revision = "fbcad9e02138"
    command.upgrade(cfg, previous_revision)

    engine = sa.create_engine(database_uri)
    version_tables = (
        ProcessInstanceCalledReleases.__table__,
        ProcessModelRelease.__table__,
        ProcessModelState.__table__,
    )
    # The squashed root uses current ORM metadata. Recreate the schema an
    # installation already at the previous revision had before this feature.
    with engine.begin() as connection:
        for table in version_tables:
            table.drop(connection, checkfirst=True)

    tenant_ids = ("m8flow", "second-tenant")
    model_id = "test/timer"
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        for tenant_id in tenant_ids:
            ensure_tenant(session, tenant_id=tenant_id)
            folder = root / tenant_id / model_id
            folder.mkdir(parents=True)
            (folder / "timer.bpmn").write_text(default_bpmn_xml(process_id="timer"), encoding="utf-8")
            definition = BpmnProcessDefinitionModel(
                m8f_tenant_id=tenant_id,
                process_xml_digest="stale-definition",
                bpmn_identifier=model_id,
                properties_json={},
            )
            session.add(SchedulerJobModel(
                m8f_tenant_id=tenant_id,
                job_key="legacy-timer",
                job_type="timer_start",
                bpmn_process_definition=definition,
                run_at=now,
                updated_at=now,
                created_at=now,
            ))

    import_legacy = versions.import_legacy

    def fail_second_import(session, tenant_id, identifier):
        model = import_legacy(session, tenant_id, identifier)
        if tenant_id == "second-tenant":
            remaining_jobs = session.scalars(sa.select(SchedulerJobModel.m8f_tenant_id)).all()
            assert remaining_jobs == ["second-tenant"]
            raise ValueError("injected legacy import failure")
        return model

    with monkeypatch.context() as patch:
        patch.setattr(versions, "import_legacy", fail_second_import)
        with pytest.raises(RuntimeError, match="tenant 'second-tenant' while importing model 'test/timer'") as exc:
            command.upgrade(cfg, "head")
    assert isinstance(exc.value.__cause__, ValueError)
    assert str(exc.value.__cause__) == "injected legacy import failure"

    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version_m8flow")) == previous_revision
        assert {table.name for table in version_tables}.isdisjoint(sa.inspect(connection).get_table_names())
        assert connection.scalars(
            sa.select(SchedulerJobModel.m8f_tenant_id).order_by(SchedulerJobModel.m8f_tenant_id),
        ).all() == list(tenant_ids)

    command.upgrade(cfg, "head")
    with Session(engine) as session:
        assert session.scalar(sa.text("SELECT version_num FROM alembic_version_m8flow")) == _script_head()
        assert session.scalars(sa.select(SchedulerJobModel)).all() == []
        for tenant_id in tenant_ids:
            model = session.get(ProcessModelState, (tenant_id, model_id))
            assert model is not None
            assert model.status == "published"
            entry, = versions.model_releases(session, model)
            assert entry.version == 1
            assert entry.published_at is None


def test_upgrade_from_legacy_connector_data_backfills_schema_and_guards_downgrade(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "legacy-connector-data.db"
    database_uri = f"sqlite:///{db_path}"
    cfg = _alembic_config(database_uri, monkeypatch)

    # Stop immediately before the additive named-value/connector-variable
    # revision, matching an existing database with legacy profile columns.
    command.upgrade(cfg, "c1e4f5a6b7d8")
    engine = sa.create_engine(database_uri)
    with engine.begin() as connection:
        profile_table = sa.Table(
            "m8flow_connector_configuration",
            sa.MetaData(),
            autoload_with=connection,
        )
        result = connection.execute(
            profile_table.insert().values(
                m8f_tenant_id="m8flow",
                connector_type="http",
                profile_name="legacy-http",
                display_name="Legacy HTTP",
                config_json={"basic_auth_username": "legacy-user"},
                secret_refs={},
                is_active=True,
                created_by_user_id=0,
            )
        )
        profile_id = result.inserted_primary_key[0]
        password_key = f"cnx_{profile_id}_basic_auth_password"
        connection.execute(
            profile_table.update()
            .where(profile_table.c.id == profile_id)
            .values(secret_refs={"basic_auth_password": password_key})
        )

        secret_table = sa.Table("secret", sa.MetaData(), autoload_with=connection)
        connection.execute(
            secret_table.insert().values(
                key=password_key,
                value="legacy-encrypted-payload",
                m8f_tenant_id="m8flow",
                created_by_user_id=0,
            )
        )
        connection.execute(
            secret_table.insert().values(
                key="API_TOKEN",
                value="legacy-named-secret-payload",
                m8f_tenant_id="m8flow",
                created_by_user_id=0,
            )
        )

    # Reaching head exercises the real predecessor ordering (including the
    # historical 1518b05122bc migration) and the configuration schema revision.
    command.upgrade(cfg, "head")
    with engine.connect() as connection:
        connector_table = sa.Table(
            "m8flow_connector_variable",
            sa.MetaData(),
            autoload_with=connection,
        )
        connector_rows = {
            row.field_name: row
            for row in connection.execute(
                sa.select(connector_table).where(
                    connector_table.c.connector_configuration_id == profile_id
                )
            ).mappings()
        }
        assert connector_rows["basic_auth_username"].is_sensitive is False
        assert connector_rows["basic_auth_username"].value == "legacy-user"
        assert connector_rows["basic_auth_password"].is_sensitive is True
        assert connector_rows["basic_auth_password"].value is None
        assert connector_rows["basic_auth_password"].provider_key == password_key

        named_values = sa.Table(
            "m8flow_named_value", sa.MetaData(), autoload_with=connection
        )
        named_secret = connection.execute(
            sa.select(named_values).where(named_values.c.name == "API_TOKEN")
        ).mappings().one()
        assert named_secret.is_sensitive is True
        assert named_secret.value is None
        assert named_secret.provider_key == "API_TOKEN"
        # Connector-owned legacy credentials remain represented only by the
        # connector variable reference, never as independently editable named
        # values.
        assert connection.execute(
            sa.select(named_values.c.id).where(
                named_values.c.m8f_tenant_id == "m8flow",
                named_values.c.provider_key == password_key,
            )
        ).first() is None

        unchanged_secret = connection.execute(
            sa.select(secret_table.c.value).where(secret_table.c.key == password_key)
        ).scalar_one()
        assert unchanged_secret == "legacy-encrypted-payload"

    with engine.connect() as connection:
        indexes = set(
            connection.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type = 'index'")
            ).scalars()
        )
    assert "uq_m8flow_named_value_tenant_name_ci" in indexes
    assert "uq_m8flow_connector_variable_field_ci" in indexes
    assert "uq_m8flow_connector_variable_field" in {
        constraint["name"]
        for constraint in sa.inspect(engine).get_unique_constraints(
            "m8flow_connector_variable"
        )
    }

    with pytest.raises(RuntimeError, match="Refusing to drop m8flow_named_value"):
        command.downgrade(cfg, "c1e4f5a6b7d8")
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version_m8flow")
        ).scalar_one() == _script_head()
    assert "m8flow_connector_variable" in sa.inspect(engine).get_table_names()


def test_upgrade_refuses_to_apply_breaking_cleanup_before_core_head(tmp_path, monkeypatch):
    db_path = tmp_path / "wrong-core-head.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    command.upgrade(cfg, "1518b05122bc")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE m8flow_core_alembic_version SET version_num = 'j1k2l3m4n5o6'"
            )
        )

    with pytest.raises(RuntimeError, match="k2l3m4n5o6p7"):
        command.upgrade(cfg, "head")


def test_upgrade_completes_missing_core_marker_for_existing_schema(tmp_path, monkeypatch):
    """DevOps does not need a separate core Alembic checkout for upgrades.

    The host owns the final handoff because the core wheel contains no
    migration scripts.  A database at the pre-breaking M8Flow head with no
    core marker must complete the equivalent final core operation and stamp it
    only after the host migration succeeds.
    """
    db_path = tmp_path / "missing-core-marker.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    command.upgrade(cfg, "b7e1c2d3f4a5")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE m8flow_core_alembic_version"))
        connection.execute(
            sa.text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(sa.text("ALTER TABLE m8f_group ADD COLUMN source_is_open_id BOOLEAN"))

    command.upgrade(cfg, "head")

    inspector = sa.inspect(engine)
    assert "source_is_open_id" not in {
        column["name"] for column in inspector.get_columns("m8f_group")
    }
    with engine.connect() as connection:
        core_stamped = connection.execute(
            sa.text("SELECT version_num FROM m8flow_core_alembic_version")
        ).scalar()
    assert core_stamped == "k2l3m4n5o6p7"


def test_upgrade_applies_core_column_cleanup_when_marker_was_preseeded(tmp_path, monkeypatch):
    """A pre-seeded core marker must not skip schema handoff operations."""
    db_path = tmp_path / "preseeded-core-marker.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    command.upgrade(cfg, "b7e1c2d3f4a5")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            sa.text("ALTER TABLE m8f_group ADD COLUMN source_is_open_id BOOLEAN")
        )

    command.upgrade(cfg, "head")

    inspector = sa.inspect(engine)
    assert "source_is_open_id" not in {
        column["name"] for column in inspector.get_columns("m8f_group")
    }


def test_upgrade_self_heals_empty_dedicated_core_marker(tmp_path, monkeypatch):
    """An existing but empty core marker is treated as an uncompleted handoff."""
    db_path = tmp_path / "empty-core-marker.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    command.upgrade(cfg, "b7e1c2d3f4a5")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM m8flow_core_alembic_version"))

    command.upgrade(cfg, "head")

    with engine.connect() as connection:
        core_stamped = connection.execute(
            sa.text("SELECT version_num FROM m8flow_core_alembic_version")
        ).scalar()
    assert core_stamped == "k2l3m4n5o6p7"


def test_upgrade_ignores_unrelated_legacy_alembic_rows(tmp_path, monkeypatch):
    """Host-owned legacy rows must not collide with the core marker."""
    db_path = tmp_path / "host-legacy-marker.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    command.upgrade(cfg, "b7e1c2d3f4a5")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE m8flow_core_alembic_version"))
        connection.execute(
            sa.text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES ('legacy-host-head')")
        )

    command.upgrade(cfg, "head")

    with engine.connect() as connection:
        core_stamped = connection.execute(
            sa.text("SELECT version_num FROM m8flow_core_alembic_version")
        ).scalar()
        legacy_stamped = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar()
    assert core_stamped == "k2l3m4n5o6p7"
    assert legacy_stamped == "legacy-host-head"


def test_upgrade_migrates_sole_legacy_core_marker(tmp_path, monkeypatch):
    """A pre-dedicated core marker is accepted and copied safely."""
    db_path = tmp_path / "legacy-core-marker.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    command.upgrade(cfg, "b7e1c2d3f4a5")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE m8flow_core_alembic_version"))
        connection.execute(
            sa.text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES ('k2l3m4n5o6p7')")
        )

    command.upgrade(cfg, "head")

    with engine.connect() as connection:
        core_stamped = connection.execute(
            sa.text("SELECT version_num FROM m8flow_core_alembic_version")
        ).scalar()
    assert core_stamped == "k2l3m4n5o6p7"


def test_followup_migration_moves_marker_for_database_at_old_head(tmp_path, monkeypatch):
    """Databases already at c4 are upgraded without replaying c4."""
    db_path = tmp_path / "old-head-marker.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE m8flow_core_alembic_version"))
        connection.execute(
            sa.text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES ('k2l3m4n5o6p7')")
        )
        connection.execute(
            sa.text(
                "UPDATE alembic_version_m8flow SET version_num = 'c4d5e6f7a8b9'"
            )
        )

    command.upgrade(cfg, "head")

    with engine.connect() as connection:
        core_stamped = connection.execute(
            sa.text("SELECT version_num FROM m8flow_core_alembic_version")
        ).scalar()
        legacy_stamped = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar()
    assert core_stamped == "k2l3m4n5o6p7"
    assert legacy_stamped == "k2l3m4n5o6p7"


def test_upgrade_rejects_mixed_legacy_core_and_host_rows(tmp_path, monkeypatch):
    """Ambiguous legacy marker ownership fails explicitly and safely."""
    db_path = tmp_path / "mixed-legacy-marker.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    command.upgrade(cfg, "b7e1c2d3f4a5")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE m8flow_core_alembic_version"))
        connection.execute(
            sa.text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO alembic_version (version_num) VALUES "
                "('k2l3m4n5o6p7'), ('legacy-host-head')"
            )
        )

    with pytest.raises(RuntimeError, match="mixed host/core revisions"):
        command.upgrade(cfg, "head")

    inspector = sa.inspect(engine)
    assert "m8flow_core_alembic_version" not in inspector.get_table_names()
    with engine.connect() as connection:
        legacy_rows = connection.execute(
            sa.text("SELECT version_num FROM alembic_version ORDER BY version_num")
        ).scalars().all()
    assert legacy_rows == ["k2l3m4n5o6p7", "legacy-host-head"]


def test_upgrade_succeeds_when_permission_target_has_no_uri(tmp_path, monkeypatch):
    """Typed core targets skip URI-only compatibility/index operations."""
    db_path = tmp_path / "typed-permission-target.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)
    command.upgrade(cfg, "b7e1c2d3f4a5")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    before_columns = {
        column["name"] for column in sa.inspect(engine).get_columns("permission_target")
    }
    assert "uri" not in before_columns

    command.upgrade(cfg, "head")

    inspector = sa.inspect(engine)
    after_columns = {
        column["name"] for column in inspector.get_columns("permission_target")
    }
    assert "uri" not in after_columns
    assert {"resource_type", "resource_id"} <= after_columns
    with engine.connect() as connection:
        sqlite_indexes = set(
            connection.execute(
                sa.text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'index' AND tbl_name = 'permission_target'"
                )
            ).scalars()
        )
    assert "m8f_permission_target_resource_command_identity_key" in sqlite_indexes
    assert "m8f_permission_target_uri_command_identity_key" not in sqlite_indexes


def test_upgrade_then_downgrade_on_empty_sqlite_is_clean(tmp_path, monkeypatch):
    db_path = tmp_path / "roundtrip.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    remaining = set(sa.inspect(engine).get_table_names())
    # The historical root creates the legacy group table; the breaking
    # migration renames it to m8f_group on upgrade. A full downgrade restores
    # that historical table shape, so it is the one expected survivor besides
    # Alembic's bookkeeping table.
    assert remaining <= {"alembic_version", "alembic_version_m8flow", "group"}


@pytest.mark.parametrize("missing", ["neither", "index", "both"])
def test_collaboration_migration_downgrade_tolerates_missing_schema(missing):
    revision = ScriptDirectory(str(_MIGRATIONS_DIR)).get_revision("e1f2a3b4c5d6").module
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "process_instance",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(255)),
        sa.Column("bpmn_process_definition_id", sa.Integer),
        sa.Column("bpmn_version_id", sa.String(255)),
    )
    column = "collaboration_correlation_key"
    index = "ix_process_instance_collaboration_lookup"

    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)) as operations:
        # Define the pre-revision schema independently of the installed core wheel.
        metadata.create_all(connection)
        if missing != "both":
            revision.upgrade()
        if missing == "index":
            operations.drop_index(index, table_name=table.name)

        revision.downgrade()
        inspector = sa.inspect(connection)
        assert column not in {item["name"] for item in inspector.get_columns(table.name)}
        assert index not in {item["name"] for item in inspector.get_indexes(table.name)}

        revision.upgrade()
        inspector = sa.inspect(connection)
        assert column in {item["name"] for item in inspector.get_columns(table.name)}
        lookup_index = next(item for item in inspector.get_indexes(table.name) if item["name"] == index)
        assert lookup_index["column_names"] == ["m8f_tenant_id", "bpmn_process_definition_id", "bpmn_version_id", column]


def test_alembic_root_downgrade_preserves_tables_added_by_newer_models(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "root-downgrade-preserves-newer-table.db"
    database_uri = f"sqlite:///{db_path}"
    cfg = _alembic_config(database_uri, monkeypatch)
    command.upgrade(cfg, "1518b05122bc")

    engine = sa.create_engine(database_uri)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE future_model_table "
                "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO future_model_table (id, value) "
                "VALUES (1, 'preserve me')"
            )
        )

    # Model the live ORM metadata gaining a table after this historical root
    # revision. The old `drop_all()` downgrade would drop this table.
    current_metadata = backend_db.combined_model_metadata()
    sa.Table(
        "future_model_table",
        current_metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )
    # Alembic loads revision modules from disk for each command, so patch the
    # source function the revision imports rather than a previously loaded copy.
    monkeypatch.setattr(
        backend_db, "combined_model_metadata", lambda: current_metadata
    )
    command.downgrade(cfg, "base")

    with engine.connect() as connection:
        preserved_value = connection.execute(
            sa.text("SELECT value FROM future_model_table WHERE id = 1")
        ).scalar_one()
    assert preserved_value == "preserve me"
    assert "m8flow_tenant" not in set(sa.inspect(engine).get_table_names())


def test_root_upgrade_fails_clearly_when_baseline_table_is_missing(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "root-upgrade-missing-model.db"
    database_uri = f"sqlite:///{db_path}"
    cfg = _alembic_config(database_uri, monkeypatch)
    monkeypatch.setattr(backend_db, "combined_model_metadata", sa.MetaData)

    with pytest.raises(RuntimeError, match="1518b05122bc migration baseline") as exc_info:
        command.upgrade(cfg, "1518b05122bc")

    assert "api_log" in str(exc_info.value)
    engine = sa.create_engine(database_uri)
    assert "m8flow_tenant" not in set(sa.inspect(engine).get_table_names())


def test_root_downgrade_validates_baseline_before_dropping_any_tables(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "root-downgrade-missing-model.db"
    database_uri = f"sqlite:///{db_path}"
    cfg = _alembic_config(database_uri, monkeypatch)
    command.upgrade(cfg, "1518b05122bc")
    monkeypatch.setattr(backend_db, "combined_model_metadata", sa.MetaData)

    with pytest.raises(RuntimeError, match="1518b05122bc migration baseline"):
        command.downgrade(cfg, "base")

    engine = sa.create_engine(database_uri)
    remaining = set(sa.inspect(engine).get_table_names())
    assert "m8flow_tenant" in remaining
    assert "m8flow_core_alembic_version" in remaining
def _journal_indexes(table: str) -> tuple[str, str]:
    return f"ix_{_JOURNAL_REVISION}_{table}_m8f_tenant_id", f"ix_{table}_process_instance_id"


@pytest.fixture(scope="module")
def journal_schema(tmp_path_factory):
    database_uri = f"sqlite:///{tmp_path_factory.mktemp('journal-schema') / 'schema.db'}"
    with pytest.MonkeyPatch.context() as patch:
        command.upgrade(_alembic_config(database_uri, patch), _JOURNAL_REVISION)
    engine = sa.create_engine(database_uri)
    metadata = sa.MetaData()
    metadata.reflect(engine, only=_JOURNAL_TABLES)
    engine.dispose()
    return metadata


def _legacy_journal_table(schema, metadata, name):
    for parent in ("m8flow_tenant", "process_instance"):
        if parent not in metadata.tables:
            sa.Table(parent, metadata, sa.Column("id", schema.tables[parent].c.id.type, primary_key=True))
    table = schema.tables[name].to_metadata(metadata)
    table.indexes.clear()
    for constraint in tuple(table.constraints):
        if isinstance(constraint, sa.CheckConstraint):
            table.constraints.remove(constraint)
        elif constraint.name is not None:
            constraint.name = f"legacy_{constraint.name}"
    return table


def _insert_journal_row(connection, table):
    values = {
        "m8f_tenant_id": "m8flow",
        "process_instance_id": 73,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "scope_id": "scope-1",
    }
    values.update({
        "compensation_scope": {"activity_id": "order", "completed": False, "data_hash": "hash"},
        "compensation_run": {
            "run_id": "run-1", "throw_task_guid": "throw-1",
            "wait_for_completion": True, "status": "running",
        },
        "compensation_record": {
            "source_task_guid": "source-1", "activity_id": "charge", "completion_sequence": 1,
            "status": "available", "attempts": 0, "data_hash": "hash",
        },
    }[table.name])
    row_id = connection.execute(table.insert().values(**values)).inserted_primary_key[0]
    return connection.execute(sa.select(table).where(table.c.id == row_id)).one()


@pytest.mark.parametrize(
    "preexisting",
    [(), _JOURNAL_TABLES, ("compensation_scope",)],
    ids=["all-new", "all-pre-existing", "mixed"],
)
def test_compensation_downgrade_preserves_preexisting_journal(tmp_path, monkeypatch, journal_schema, preexisting):
    database_uri = f"sqlite:///{tmp_path / 'journal.db'}"
    cfg = _alembic_config(database_uri, monkeypatch)
    previous_revision = "c1e4f5a6b7d8"
    command.upgrade(cfg, previous_revision)

    engine = sa.create_engine(database_uri)
    metadata = sa.MetaData()
    for name in _JOURNAL_TABLES:
        # Include a pre-existing table whose index collides with the legacy ownership marker.
        index_name = _journal_indexes(name)[0] if name == "compensation_scope" else f"ix_{name}_m8f_tenant_id"
        table = _legacy_journal_table(journal_schema, metadata, name)
        if name != "compensation_run":
            sa.Index(index_name, table.c.m8f_tenant_id)
    original_rows = {}
    with engine.begin() as connection:
        # Set up the same legacy layout even when the root ORM creates journal tables.
        for name in reversed(_JOURNAL_TABLES):
            metadata.tables[name].drop(connection, checkfirst=True)
        for name in preexisting:
            table = metadata.tables[name]
            table.create(connection)
            original_rows[name] = _insert_journal_row(connection, table)

    command.upgrade(cfg, "head")
    assert set(_JOURNAL_TABLES) <= set(sa.inspect(engine).get_table_names())

    with engine.begin() as connection:
        for name in set(_JOURNAL_TABLES) - set(preexisting):
            for index in _journal_indexes(name):
                connection.execute(sa.DDL(f"DROP INDEX {index}"))

    command.downgrade(cfg, previous_revision)
    remaining = set(sa.inspect(engine).get_table_names())
    assert set(_JOURNAL_TABLES) & remaining == set(preexisting)
    assert _JOURNAL_OWNERSHIP not in remaining

    command.upgrade(cfg, "head")
    with engine.connect() as connection:
        inspector = sa.inspect(connection)
        assert set(_JOURNAL_TABLES) <= set(inspector.get_table_names())
        for name in _JOURNAL_TABLES:
            indexes = {index["name"] for index in inspector.get_indexes(name)}
            tenant_index, process_index = _journal_indexes(name)
            foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(name)}
            marker = f"fk_{_JOURNAL_REVISION}_{name}_tenant"
            if name in preexisting:
                table = metadata.tables[name]
                assert marker not in foreign_keys
                original_indexes = {index.name for index in table.indexes}
                assert indexes == (original_indexes or {tenant_index}) | {process_index}
                assert connection.execute(sa.select(table)).all() == [original_rows[name]]
            else:
                assert marker in foreign_keys
                assert set(_journal_indexes(name)) <= indexes
    engine.dispose()


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("minimal", "missing columns"),
        ("type", "status has type"),
        ("nullability", "status must be NOT NULL"),
        ("primary-key", "expected a primary key"),
        ("generated-id", "id must be generated automatically"),
        ("unique", "expected unique constraints"),
        ("unique-index", "unexpected standalone unique indexes: legacy_unique_record"),
        ("unique-expression-index", "unexpected standalone unique indexes: legacy_unique_record"),
        ("foreign-key", "expected foreign keys"),
    ],
)
def test_compensation_upgrade_rejects_incompatible_existing_table(
    tmp_path, monkeypatch, journal_schema, defect, message
):
    database_uri = f"sqlite:///{tmp_path / 'journal-incompatible.db'}"
    cfg = _alembic_config(database_uri, monkeypatch)
    previous_revision = "c1e4f5a6b7d8"
    command.upgrade(cfg, previous_revision)

    engine = sa.create_engine(database_uri)
    metadata = sa.MetaData()
    scope = _legacy_journal_table(journal_schema, metadata, "compensation_scope")
    name = "compensation_record"
    if defect == "minimal":
        table = sa.Table(
            name, metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
            sa.Column("process_instance_id", sa.Integer, nullable=False),
        )
    else:
        table = _legacy_journal_table(journal_schema, metadata, name)
        if defect == "type":
            table.c.status.type = sa.String(5)
        elif defect == "nullability":
            table.c.status.nullable = True
        elif defect == "primary-key":
            table.c.id.primary_key = False
            table.append_constraint(sa.PrimaryKeyConstraint("completion_sequence"))
        elif defect == "generated-id":
            table.dialect_options["sqlite"]["with_rowid"] = False
        elif defect == "unique":
            sequence_key = next(
                constraint for constraint in table.constraints
                if isinstance(constraint, sa.UniqueConstraint) and "completion_sequence" in constraint.columns
            )
            table.constraints.remove(sequence_key)
        elif defect == "foreign-key":
            process_fk = next(
                constraint for constraint in table.foreign_key_constraints
                if "process_instance_id" in constraint.columns
            )
            table.constraints.remove(process_fk)

    with engine.begin() as connection:
        # The root ORM may already have created the journal tables.
        for journal in reversed(_JOURNAL_TABLES):
            connection.execute(sa.DDL(f"DROP TABLE IF EXISTS {journal}"))
        scope.create(connection)
        table.create(connection)
        if defect == "unique-index":
            sa.Index("legacy_unique_record", table.c.process_instance_id, unique=True).create(connection)
        elif defect == "unique-expression-index":
            sa.Index("legacy_unique_record", sa.func.lower(table.c.activity_id), unique=True).create(connection)
        legacy_indexes = sa.text("SELECT name FROM pragma_index_list(:table) WHERE origin = 'c'")
        original_indexes = connection.scalars(legacy_indexes, {"table": name}).all()
        # Seed through the valid sibling table to check that the preflight leaves it alone.
        scope_row = _insert_journal_row(connection, scope)
        if defect == "minimal":
            connection.execute(table.insert().values(id=42, m8f_tenant_id="m8flow", process_instance_id=73))

    with pytest.raises(RuntimeError, match=rf"{name}.*{message}.*Back up and rename"):
        command.upgrade(cfg, "head")

    inspector = sa.inspect(engine)
    assert not inspector.has_table("compensation_run")
    assert not inspector.has_table(_JOURNAL_OWNERSHIP)
    assert inspector.get_indexes(scope.name) == []
    with engine.connect() as connection:
        assert connection.scalars(legacy_indexes, {"table": name}).all() == original_indexes
        assert connection.execute(sa.select(scope)).all() == [scope_row]
        if defect == "minimal":
            assert connection.execute(sa.select(table)).all() == [(42, "m8flow", 73)]
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version_m8flow")) == previous_revision
    engine.dispose()


def test_compensation_downgrade_keeps_preexisting_ownership_table(tmp_path, monkeypatch):
    database_uri = f"sqlite:///{tmp_path / 'journal-ownership.db'}"
    cfg = _alembic_config(database_uri, monkeypatch)
    previous_revision = "c1e4f5a6b7d8"
    command.upgrade(cfg, previous_revision)

    engine = sa.create_engine(database_uri)
    ownership = sa.Table(
        _JOURNAL_OWNERSHIP,
        sa.MetaData(),
        sa.Column("table_name", sa.String(63), primary_key=True),
        sa.Column("creation_marker", sa.String(63), nullable=False),
    )
    with engine.begin() as connection:
        # The root ORM may already have created the journal tables; start without them.
        for name in _JOURNAL_TABLES:
            connection.execute(sa.DDL(f"DROP TABLE IF EXISTS {name}"))
        ownership.create(connection)
        connection.execute(ownership.insert().values(table_name="other_tool_table", creation_marker="x"))

    command.upgrade(cfg, "head")
    command.downgrade(cfg, previous_revision)

    inspector = sa.inspect(engine)
    assert not set(_JOURNAL_TABLES) & set(inspector.get_table_names())
    assert inspector.has_table(_JOURNAL_OWNERSHIP)
    with engine.connect() as connection:
        assert connection.execute(sa.select(ownership)).all() == [("other_tool_table", "x")]
    engine.dispose()


@pytest.mark.parametrize("replace_table", [False, True], ids=["interrupted-upgrade", "replacement-table"])
def test_compensation_reconciles_indexes_and_requires_creation_record(
    tmp_path, monkeypatch, journal_schema, replace_table
):
    database_uri = f"sqlite:///{tmp_path / 'partial-journal.db'}"
    cfg = _alembic_config(database_uri, monkeypatch)
    previous_revision = "c1e4f5a6b7d8"
    command.upgrade(cfg, _JOURNAL_REVISION)

    engine = sa.create_engine(database_uri)
    name = "compensation_scope"
    tenant_index, process_index = _journal_indexes(name)
    metadata = sa.MetaData()
    with engine.begin() as connection:
        if replace_table:
            table = _legacy_journal_table(journal_schema, metadata, name)
            tenant_fk = next(
                constraint for constraint in table.foreign_key_constraints if "m8f_tenant_id" in constraint.columns
            )
            tenant_fk.name = f"fk_{_JOURNAL_REVISION}_{name}_tenant"
            table.drop(connection)
            table.create(connection)
            original_row = _insert_journal_row(connection, table)
        else:
            for index in (tenant_index, process_index):
                connection.execute(sa.DDL(f"DROP INDEX {index}"))

    # Retry the revision against the existing tables as after an interrupted upgrade.
    command.stamp(cfg, previous_revision)
    command.upgrade(cfg, "head")
    indexes = {index["name"] for index in sa.inspect(engine).get_indexes(name)}
    assert indexes == {tenant_index, process_index}

    command.downgrade(cfg, previous_revision)
    assert sa.inspect(engine).has_table(name) == replace_table
    assert not sa.inspect(engine).has_table(_JOURNAL_OWNERSHIP)
    if replace_table:
        with engine.connect() as connection:
            assert connection.execute(sa.select(table)).all() == [original_row]
    engine.dispose()


def test_compensation_table_and_creation_record_roll_back_together(tmp_path, monkeypatch):
    database_uri = f"sqlite:///{tmp_path / 'journal-index-failure.db'}"
    cfg = _alembic_config(database_uri, monkeypatch)
    previous_revision = "c1e4f5a6b7d8"
    command.upgrade(cfg, previous_revision)
    create_index = op.create_index

    def fail_journal_index(index_name, *args, **kwargs):
        if index_name == _journal_indexes("compensation_scope")[0]:
            raise RuntimeError("simulated journal index failure")
        return create_index(index_name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(op, "create_index", fail_journal_index)
        with pytest.raises(RuntimeError, match="simulated journal index failure"):
            command.upgrade(cfg, _JOURNAL_REVISION)

    engine = sa.create_engine(database_uri)
    assert not sa.inspect(engine).has_table("compensation_scope")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, previous_revision)
    assert not sa.inspect(engine).has_table("compensation_scope")
    engine.dispose()


@pytest.mark.parametrize("equivalent_index", [False, True], ids=["occupied-name", "equivalent-index"])
def test_compensation_indexes_respect_sqlite_schema_names(tmp_path, monkeypatch, journal_schema, equivalent_index):
    database_uri = f"sqlite:///{tmp_path / 'journal-index-names.db'}"
    cfg = _alembic_config(database_uri, monkeypatch)
    previous_revision = "c1e4f5a6b7d8"
    command.upgrade(cfg, previous_revision)

    engine = sa.create_engine(database_uri)
    metadata = sa.MetaData()
    name = "compensation_scope"
    tenant_index, process_index = _journal_indexes(name)
    table = _legacy_journal_table(journal_schema, metadata, name)
    unrelated = sa.Table("legacy_index_owner", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Index(process_index.upper(), unrelated.c.id)
    if equivalent_index:
        sa.Index("legacy_scope_by_instance", table.c.process_instance_id)

    with engine.begin() as connection:
        table.drop(connection, checkfirst=True)
        table.create(connection)
        unrelated.create(connection)
        original_row = _insert_journal_row(connection, table)

    command.upgrade(cfg, "head")
    expected = "legacy_scope_by_instance" if equivalent_index else f"{process_index}_2"
    assert {index["name"] for index in sa.inspect(engine).get_indexes(name)} == {tenant_index, expected}
    assert {index["name"] for index in sa.inspect(engine).get_indexes(unrelated.name)} == {process_index.upper()}

    command.downgrade(cfg, previous_revision)
    with engine.connect() as connection:
        assert connection.execute(sa.select(table)).all() == [original_row]
    engine.dispose()


def test_upgrade_head_self_heals_a_pre_squash_stamp(tmp_path, monkeypatch):
    """A database stamped at a now-deleted revision must recover automatically.

    This is the case that stranded existing databases after the squash: the old
    chain left a head revision id (e.g. ``v6g7h8i9j0k1``) that no longer exists,
    so ``upgrade head`` used to abort with "Can't locate revision". env.py now
    clears the stale marker and replays the idempotent root instead.
    """
    db_path = tmp_path / "legacy.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)

    # Build the schema, then forge a pre-squash stamp Alembic can't resolve.
    command.upgrade(cfg, "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE alembic_version_m8flow SET version_num = 'v6g7h8i9j0k1'")
        )

    # Must not raise, and must land back on the real chain — data preserved.
    command.upgrade(cfg, "head")

    with engine.connect() as connection:
        stamped = connection.execute(
            sa.text("SELECT version_num FROM alembic_version_m8flow")
        ).scalar()
        seeded = connection.execute(
            sa.text("SELECT slug FROM m8flow_tenant WHERE id = 'm8flow'")
        ).scalar()
    assert stamped == _script_head()
    assert seeded == "m8flow"


@pytest.mark.skipif(
    not os.environ.get("M8FLOW_TEST_POSTGRES_URI"),
    reason="Set M8FLOW_TEST_POSTGRES_URI to an empty, disposable database to run the RLS check.",
)
def test_upgrade_head_on_empty_postgres_applies_rls_and_seed(monkeypatch):
    database_uri = os.environ["M8FLOW_TEST_POSTGRES_URI"]
    cfg = _alembic_config(database_uri, monkeypatch)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(database_uri)
    with engine.connect() as connection:
        missing = _orm_table_names() - set(sa.inspect(connection).get_table_names())
        assert not missing, f"upgrade head left tables uncreated: {sorted(missing)}"

        # Every tenant-scoped table (incl. scheduler_job, which used to get its
        # RLS in a separate late revision) carries the policy pair.
        for table in (
            "process_instance",
            "secret",
            "scheduler_job",
            "m8flow_nats_event_audit",
            "m8flow_nats_api_keys",
            "m8flow_process_instance_error",
            "compensation_scope",
            "compensation_run",
            "compensation_record",
        ):
            policies = connection.execute(
                sa.text("SELECT policyname FROM pg_policies WHERE tablename = :t"),
                {"t": table},
            ).scalars().all()
            assert f"{table}_tenant_isolation" in policies, table
            assert f"{table}_super_admin_select" in policies, table

        # Host-only uniqueness constraint the core ORM omits.
        user_uniques = {
            c["name"] for c in sa.inspect(connection).get_unique_constraints("user")
        }
        assert "uq_user_username_realm" in user_uniques

        seeded = connection.execute(
            sa.text("SELECT slug FROM m8flow_tenant WHERE id = 'm8flow'")
        ).scalar()
        assert seeded == "m8flow"


@pytest.mark.skipif(
    not os.environ.get("M8FLOW_TEST_POSTGRES_URI"),
    reason="Set M8FLOW_TEST_POSTGRES_URI to an empty, disposable database to run the RLS check.",
)
def test_process_model_version_downgrade_removes_postgres_rls_tables(monkeypatch, tmp_path):
    from m8flow_backend.models.process_model_version import (
        ProcessInstanceCalledReleases,
        ProcessModelRelease,
        ProcessModelState,
    )

    database_uri = os.environ["M8FLOW_TEST_POSTGRES_URI"]
    cfg = _alembic_config(database_uri, monkeypatch)
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    table_names = {
        ProcessModelState.__tablename__,
        ProcessModelRelease.__tablename__,
        ProcessInstanceCalledReleases.__tablename__,
    }
    policies = sa.text(
        "SELECT policyname FROM pg_policies WHERE schemaname = current_schema() AND tablename = :table_name"
    )

    command.upgrade(cfg, "head")
    engine = sa.create_engine(database_uri)
    with engine.connect() as connection:
        for table_name in table_names:
            assert {"tenant_scope", "tenant_read_all"} <= set(
                connection.scalars(policies, {"table_name": table_name})
            )
            assert connection.scalar(sa.text(
                "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:table_name)"
            ), {"table_name": table_name}) is True

    try:
        previous_revision = "fbcad9e02138"
        # Unmerge first, then drop versioning without rolling back main's branch.
        command.downgrade(cfg, previous_revision)
        command.downgrade(cfg, "e2f3a4b5c6d7@d1e2f3a4b5c6")
        with engine.connect() as connection:
            assert connection.scalars(sa.text("SELECT version_num FROM alembic_version_m8flow")).all() == [
                previous_revision,
            ]
            assert table_names.isdisjoint(sa.inspect(connection).get_table_names())
            for table_name in table_names:
                assert connection.scalars(policies, {"table_name": table_name}).all() == []
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()


@pytest.mark.skipif(
    not os.environ.get("M8FLOW_TEST_POSTGRES_URI"),
    reason="Set M8FLOW_TEST_POSTGRES_URI to an empty, disposable database to run the RLS check.",
)
def test_upgrade_from_previous_head_puts_rls_on_process_instance_error(monkeypatch):
    """A database stamped at f4254352d453 gets this table from b7e1c2d3f4a5,
    not from the root revision's create_all + RLS pass, so that revision must
    apply the policy pair itself."""
    table = "m8flow_process_instance_error"
    database_uri = os.environ["M8FLOW_TEST_POSTGRES_URI"]
    cfg = _alembic_config(database_uri, monkeypatch)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(database_uri)
    with engine.begin() as connection:
        connection.execute(sa.text(f"DROP TABLE {table}"))
    command.stamp(cfg, "f4254352d453")

    command.upgrade(cfg, "head")

    with engine.connect() as connection:
        row_security = connection.execute(
            sa.text("SELECT relrowsecurity FROM pg_class WHERE relname = :t"), {"t": table}
        ).scalar()
        policies = connection.execute(
            sa.text("SELECT policyname FROM pg_policies WHERE tablename = :t"), {"t": table}
        ).scalars().all()
    assert row_security is True
    assert {f"{table}_tenant_isolation", f"{table}_super_admin_select"} <= set(policies)


@pytest.mark.skipif(
    not os.environ.get("M8FLOW_TEST_POSTGRES_URI"),
    reason="Set M8FLOW_TEST_POSTGRES_URI to a disposable database to test journal upgrades.",
)
def test_compensation_journal_upgrade_applies_tenant_rls(monkeypatch):
    database_uri = os.environ["M8FLOW_TEST_POSTGRES_URI"]
    cfg = _alembic_config(database_uri, monkeypatch)
    previous_revision = "c1e4f5a6b7d8"
    command.upgrade(cfg, "head")
    engine = sa.create_engine(database_uri)
    adopted_table = "compensation_scope"
    ownership = sa.table(_JOURNAL_OWNERSHIP, sa.column("table_name"))
    with engine.begin() as connection:
        connection.execute(ownership.delete().where(ownership.c.table_name == adopted_table))
    command.downgrade(cfg, previous_revision)

    preexisting = set(_JOURNAL_TABLES) & set(sa.inspect(engine).get_table_names())
    assert adopted_table in preexisting
    with engine.begin() as connection:
        connection.execute(sa.DDL("ALTER TABLE compensation_scope DISABLE ROW LEVEL SECURITY"))
        connection.execute(sa.DDL("DROP POLICY IF EXISTS compensation_scope_tenant_isolation ON compensation_scope"))
        connection.execute(sa.DDL("DROP INDEX IF EXISTS ix_compensation_scope_process_instance_id"))

    command.upgrade(cfg, "head")
    with engine.begin() as connection:
        assert connection.scalar(sa.select(ownership.c.table_name).where(
            ownership.c.table_name == adopted_table
        )) is None
        assert _journal_indexes(adopted_table)[1] in {
            index["name"] for index in sa.inspect(connection).get_indexes(adopted_table)
        }
        for table in _JOURNAL_TABLES:
            assert connection.scalar(sa.text(
                "SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(:table)"
            ), {"table": table}) is True
            policies = connection.execute(sa.text(
                "SELECT policyname FROM pg_policies WHERE tablename = :table"
            ), {"table": table}).scalars().all()
            assert set(policies) == {f"{table}_tenant_isolation", f"{table}_super_admin_select"}
            if table not in preexisting:
                for index in _journal_indexes(table):
                    connection.execute(sa.DDL(f"DROP INDEX {index}"))

    command.downgrade(cfg, previous_revision)
    assert set(_JOURNAL_TABLES) & set(sa.inspect(engine).get_table_names()) == preexisting
    command.upgrade(cfg, "head")
    engine.dispose()
