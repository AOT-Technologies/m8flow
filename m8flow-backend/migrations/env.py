from __future__ import annotations

import logging
import os

import sqlalchemy as sa
from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, engine_from_config, pool

from m8flow_backend.db import alembic_target_metadata

config = context.config
target_metadata = alembic_target_metadata()

VERSION_TABLE = "alembic_version_m8flow"
LOGGER = logging.getLogger("m8flow.migrations")

for name in ("alembic", "alembic.runtime.migration"):
    lg = logging.getLogger(name)
    lg.handlers = []
    lg.propagate = True


def get_url():
    url = os.environ.get("M8FLOW_BACKEND_DATABASE_URI") or os.environ.get("M8FLOW_DATABASE_URI")
    if not url:
        raise RuntimeError("Set M8FLOW_BACKEND_DATABASE_URI or M8FLOW_DATABASE_URI for Alembic.")
    return url


def _reconcile_pre_squash_stamp(connection: Connection) -> None:
    """Self-heal databases stamped by the retired pre-squash migration chain.

    The incremental chain was squashed into the single root revision
    ``1518b05122bc``. A database created by the old chain is stamped at a head
    revision (e.g. ``v6g7h8i9j0k1``) whose script no longer exists, so every
    ``alembic upgrade head`` would abort with
    ``Can't locate revision identified by '<old head>'`` and the backend would
    crash-loop.

    When the recorded revision is unknown to the current scripts, clear the
    version marker so the consolidated root revision replays. The root is
    idempotent - ``create_all`` is ``checkfirst`` and the RLS / seed / unique
    steps are guarded - so replaying against an already-populated database
    leaves existing tables and data intact and simply re-stamps to head.

    A fresh database (no version table) and a healthy database (already stamped
    at a known revision) both no-op here.
    """
    inspector = sa.inspect(connection)
    if VERSION_TABLE not in inspector.get_table_names():
        return

    recorded = connection.execute(sa.text(f"SELECT version_num FROM {VERSION_TABLE}")).scalars().all()
    if not recorded:
        return

    known = {script.revision for script in ScriptDirectory.from_config(config).walk_revisions()}
    stranded = sorted(set(recorded) - known)
    if not stranded:
        return

    LOGGER.warning(
        "Database is stamped at revision(s) %s that no longer exist after the "
        "migration squash. Clearing the Alembic version marker so the "
        "consolidated root migration replays idempotently; existing tables and "
        "data are preserved.",
        stranded,
    )
    connection.execute(sa.text(f"DELETE FROM {VERSION_TABLE}"))


def run_migrations_online():
    connectable = engine_from_config(
        {"sqlalchemy.url": get_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version_m8flow",
            compare_type=True,
        )
        with context.begin_transaction():
            _reconcile_pre_squash_stamp(connection)
            context.run_migrations()


run_migrations_online()
