"""Postgres harness for the host-on-core integration suite.

Opt-in: set ``M8FLOW_TEST_POSTGRES_URI`` to a PostgreSQL role that may
CREATE DATABASE and CREATE ROLE (any database on that server works as the
entry point). Without it every test here is skipped.

Each xdist worker gets its own database, migrated with the real Alembic chain
(host revisions plus the pinned core wheel's models), and its own runtime role
that is neither superuser nor BYPASSRLS. The host connects as that runtime
role, so core's queries run under the same row-level security as production.
Tests isolate from each other with fresh tenant ids, not fresh databases.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

POSTGRES_URI_ENV = "M8FLOW_TEST_POSTGRES_URI"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = BACKEND_ROOT / "tests" / "fixtures"


@dataclass(frozen=True)
class MigratedDatabase:
    admin_uri: str  # migration role: owner, bypasses RLS
    runtime_uri: str  # app role: RLS applies


def _admin_server_uri() -> str:
    uri = os.environ.get(POSTGRES_URI_ENV, "").strip()
    if not uri:
        pytest.skip(f"Set {POSTGRES_URI_ENV} to a PostgreSQL role with CREATEDB and CREATEROLE.")
    if make_url(uri).get_backend_name() != "postgresql":
        pytest.skip(f"{POSTGRES_URI_ENV} must point at PostgreSQL.")
    return uri


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[MigratedDatabase]:
    from alembic import command
    from alembic.config import Config

    server = make_url(_admin_server_uri())
    # Not the xdist `worker_id` fixture: it is missing when xdist is not loaded.
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    suffix = f"{worker}_{uuid.uuid4().hex[:8]}"
    db_name = f"m8flow_it_{suffix}"
    role = f"m8flow_it_rt_{suffix}"
    password = uuid.uuid4().hex

    bootstrap = sa.create_engine(server, isolation_level="AUTOCOMMIT")
    admin_uri = server.set(database=db_name).render_as_string(hide_password=False)
    runtime_uri = server.set(database=db_name, username=role, password=password).render_as_string(
        hide_password=False
    )
    try:
        with bootstrap.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
            # DDL takes no bind parameters; the password is a generated hex string.
            conn.execute(sa.text(f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{password}' NOSUPERUSER NOBYPASSRLS"))

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("M8FLOW_BACKEND_DATABASE_URI", admin_uri)
            mp.delenv("M8FLOW_DATABASE_URI", raising=False)
            mp.setenv("M8FLOW_BACKEND_ENV", "unit_testing")
            cfg = Config()
            cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
            command.upgrade(cfg, "head")

        admin = sa.create_engine(admin_uri)
        with admin.begin() as conn:
            conn.execute(sa.text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
            conn.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"'))
            conn.execute(sa.text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"'))
        admin.dispose()

        yield MigratedDatabase(admin_uri=admin_uri, runtime_uri=runtime_uri)
    finally:
        from m8flow_backend.db import reset_engine

        reset_engine()
        with bootstrap.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
            conn.execute(sa.text(f'DROP ROLE IF EXISTS "{role}"'))
        bootstrap.dispose()


@pytest.fixture
def host_db(migrated_database: MigratedDatabase, monkeypatch, tmp_path) -> Iterator[MigratedDatabase]:
    """Boot the host against the runtime role, as production does.

    ``create_app()`` is what installs the host authorization policy, the
    service-task registry, and the core engine hooks into core; without it
    core falls back to its own defaults and the tests would not exercise the
    host-on-core seam. ``install_postgres_rls_hook`` is idempotent and also
    runs inside ``create_app()``; calling it here keeps the dependency explicit.
    """
    from m8flow_backend.app import create_app
    from m8flow_backend.auth.bind import install_postgres_rls_hook
    from m8flow_backend.db import reset_engine

    monkeypatch.setenv("M8FLOW_BACKEND_DATABASE_URI", migrated_database.runtime_uri)
    monkeypatch.delenv("M8FLOW_DATABASE_URI", raising=False)
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "specs"))
    reset_engine()
    create_app()
    install_postgres_rls_hook()
    yield migrated_database
    reset_engine()


@pytest.fixture
def admin_engine(migrated_database: MigratedDatabase) -> Iterator[sa.Engine]:
    """Owner connection that sees every tenant: for cross-tenant assertions only."""
    engine = sa.create_engine(migrated_database.admin_uri)
    yield engine
    engine.dispose()
