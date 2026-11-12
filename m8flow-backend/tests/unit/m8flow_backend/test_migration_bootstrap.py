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
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from m8flow_backend.db import alembic_target_metadata

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
def _script_head() -> str:
    """The chain's current head. Asserted against the stamp rather than a literal so
    adding an ordinary incremental revision on top of the squashed root does not read
    as the NoSuchTableError regression these tests exist to catch."""
    from alembic.script import ScriptDirectory

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
