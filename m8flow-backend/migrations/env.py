from __future__ import annotations

import logging
import os

import sqlalchemy as sa
from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, engine_from_config, pool

from m8flow_backend.db import alembic_target_metadata
from m8flow_backend.migration_compatibility import (
    OWNERSHIP_TABLE,
    core_revision,
    host_revision,
    legacy_ownership_table,
    prepare_compensation_replay,
    require_message_schema,
)

config = context.config
target_metadata = alembic_target_metadata()

VERSION_TABLE = "alembic_version_m8flow"
LOGGER = logging.getLogger("m8flow.migrations")
TRANSACTIONAL_DDL_DIALECTS = frozenset({"postgresql", "sqlite"})

for name in ("alembic", "alembic.runtime.migration"):
    lg = logging.getLogger(name)
    lg.handlers = []
    lg.propagate = True


def get_url():
    url = os.environ.get("M8FLOW_BACKEND_DATABASE_URI") or os.environ.get("M8FLOW_DATABASE_URI")
    if not url:
        raise RuntimeError("Set M8FLOW_BACKEND_DATABASE_URI or M8FLOW_DATABASE_URI for Alembic.")
    return url


def _reconcile_legacy_message_revisions(connection: Connection) -> None:
    """Adopt recognized historical names without replaying their schema DDL."""
    if not sa.inspect(connection).has_table(VERSION_TABLE):
        return
    version = sa.table(VERSION_TABLE, sa.column("version_num"))
    recorded = set(connection.scalars(sa.select(version.c.version_num)))
    aliases = {value: host_revision(value) for value in recorded}
    if len(set(aliases.values())) != len(recorded):
        raise RuntimeError("Duplicate historical host revision mappings; reconcile before upgrading.")
    legacy_ownership = legacy_ownership_table(connection)
    if any(value != current for value, current in aliases.items()):
        require_message_schema(connection)
    for value, current in aliases.items():
        if value != current:
            connection.execute(version.update().where(version.c.version_num == value).values(version_num=current))
    if legacy_ownership is None:
        return
    # Begin SQLite's write transaction even when the host stamp is neutral.
    connection.execute(version.update().where(sa.false()).values(version_num="core_message_schema"))
    quote = connection.dialect.identifier_preparer.quote
    connection.execute(sa.DDL(f"ALTER TABLE {quote(legacy_ownership)} RENAME TO {quote(OWNERSHIP_TABLE)}"))
    ownership = sa.table(OWNERSHIP_TABLE, sa.column("table_name"), sa.column("creation_marker"))
    connection.execute(ownership.update().where(ownership.c.table_name == legacy_ownership).values(
        table_name=OWNERSHIP_TABLE, creation_marker="core_message_schema",
    ))


def _reconcile_legacy_core_message_marker(connection: Connection) -> None:
    """Normalize an installed core schema even when the host is already at head."""
    name = "m8flow_core_alembic_version"
    if not sa.inspect(connection).has_table(name):
        # A standalone core installation may predate the dedicated host table.
        # Copy its verified handoff without changing the generic version table.
        if sa.inspect(connection).has_table("alembic_version"):
            legacy = sa.table("alembic_version", sa.column("version_num"))
            recorded = list(connection.scalars(sa.select(legacy.c.version_num)))
            recognized = [
                value for value in recorded
                if (value == "message_correlation" or value.lower().endswith("_message_correlation"))
                and core_revision(value) == "message_correlation"
            ]
            if recognized:
                if len(recorded) != 1:
                    raise RuntimeError("Legacy alembic_version contains mixed host/core revisions")
                require_message_schema(connection)
                table = sa.Table(name, sa.MetaData(), sa.Column("version_num", sa.String(32), primary_key=True))
                table.create(connection)
                connection.execute(table.insert().values(version_num="k2l3m4n5o6p7"))
        return
    version = sa.table(name, sa.column("version_num"))
    recorded = list(connection.scalars(sa.select(version.c.version_num)))
    # This table records the host/core handoff, not the standalone core chain.
    # Keep the baseline required by historical host migrations on replay.
    aliases = {
        value: "k2l3m4n5o6p7" if core_revision(value) == "message_correlation" else value
        for value in recorded
    }
    if all(value == current for value, current in aliases.items()):
        return
    if len(recorded) != 1:
        raise RuntimeError(f"Ambiguous core migration markers; reconcile before upgrading: {recorded!r}")
    require_message_schema(connection)
    connection.execute(version.update().where(version.c.version_num == recorded[0]).values(
        version_num=aliases[recorded[0]],
    ))


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

    version_table = sa.table(VERSION_TABLE, sa.column("version_num"))
    recorded = connection.execute(sa.select(version_table.c.version_num)).scalars().all()
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
    connection.execute(sa.delete(version_table))


def run_migrations_online():
    connectable = engine_from_config(
        {"sqlalchemy.url": get_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # The 0.2.1 core handoff contains destructive table recreation and
        # column drops. PostgreSQL and SQLite can roll those DDL operations
        # back with the surrounding Alembic transaction. MySQL/MariaDB may
        # implicitly commit DDL, so the breaking-migration runbook requires a
        # verified backup and restore-based recovery for those dialects.
        options = dict(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version_m8flow",
            compare_type=True,
            transactional_ddl=connection.dialect.name in TRANSACTIONAL_DDL_DIALECTS,
        )
        context.configure(**options)
        migration_fn = context.get_context().opts["fn"]
        scripts = ScriptDirectory.from_config(config)

        def compatible_steps(revisions, migration_context):
            for step in migration_fn(revisions, migration_context):
                if step.is_upgrade and step.revision.revision == "fa8b9c0d1e2f":
                    prepare_compensation_replay(connection, migration_context, scripts)
                yield step

        context.configure(**options, fn=compatible_steps)
        with context.begin_transaction():
            _reconcile_legacy_message_revisions(connection)
            _reconcile_legacy_core_message_marker(connection)
            _reconcile_pre_squash_stamp(connection)
            context.run_migrations()


run_migrations_online()
