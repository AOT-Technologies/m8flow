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
_ROOT_REVISION = "1518b05122bc"


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

    # Single self-sufficient revision is stamped as head.
    with engine.connect() as connection:
        stamped = connection.execute(
            sa.text("SELECT version_num FROM alembic_version_m8flow")
        ).scalar()
    assert stamped == _ROOT_REVISION

    # Base tenant seed lands regardless of dialect.
    with engine.connect() as connection:
        seeded = connection.execute(
            sa.text("SELECT slug FROM m8flow_tenant WHERE id = 'm8flow'")
        ).scalar()
    assert seeded == "m8flow"


def test_upgrade_then_downgrade_on_empty_sqlite_is_clean(tmp_path, monkeypatch):
    db_path = tmp_path / "roundtrip.db"
    cfg = _alembic_config(f"sqlite:///{db_path}", monkeypatch)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    remaining = set(sa.inspect(engine).get_table_names())
    # Only Alembic's own bookkeeping table should survive a full downgrade.
    assert remaining <= {"alembic_version_m8flow"}


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

    # Must not raise, and must land back on the real root — data preserved.
    command.upgrade(cfg, "head")

    with engine.connect() as connection:
        stamped = connection.execute(
            sa.text("SELECT version_num FROM alembic_version_m8flow")
        ).scalar()
        seeded = connection.execute(
            sa.text("SELECT slug FROM m8flow_tenant WHERE id = 'm8flow'")
        ).scalar()
    assert stamped == _ROOT_REVISION
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
        for table in ("process_instance", "secret", "scheduler_job"):
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
