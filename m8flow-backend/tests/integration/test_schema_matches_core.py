"""The PostgreSQL schema Alembic builds must match the pinned core ORM.

A new core wheel that adds a column, table, index, or constraint, or changes a
type or nullability, needs a host migration. Without one, core's queries fail
at runtime on PostgreSQL. This compares the database migrated to ``head``
against core's metadata, limited to core-owned tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

# Known, reviewed differences between core's ORM and the host-migrated schema.
# (kind, table, columns). Anything else on a core table fails the test.
KNOWN_DIFFERENCES = {
    # Host migration adds an expression index for command-aware target identity.
    ("remove_index", "permission_target", ("resource_type", "resource_id", "<expr>")),
    # Host keeps the pre-0.2.1 (username, service) uniqueness the core ORM omits.
    ("remove_constraint", "user", ("username", "service")),
    # Core declares UniqueConstraint(work_item_id, user_id); the host schema
    # enforces the same pair as the primary key (pk_work_item_user).
    ("add_constraint", "work_item_user", ("work_item_id", "user_id")),
}


def _signature(item: tuple) -> tuple[str, str, tuple[str, ...]] | None:
    kind = item[0]
    if kind in {"add_table", "remove_table"}:
        return kind, item[1].name, ()
    if kind in {"add_column", "remove_column"}:
        return kind, item[2], (item[3].name,)
    if kind.startswith("modify_"):
        return kind, item[2], (item[3],)
    if kind in {"add_index", "remove_index", "add_constraint", "remove_constraint"}:
        obj = item[1]
        columns = tuple(
            getattr(expr, "name", None) or "<expr>" for expr in getattr(obj, "expressions", None) or obj.columns
        )
        return kind, obj.table.name, columns
    if kind in {"add_fk", "remove_fk"}:
        fk = item[1]
        return kind, fk.parent.name, tuple(c.name for c in fk.columns)
    return None


def test_migrated_postgres_schema_matches_core_orm(admin_engine):
    from m8flow_core.models.base import Base as CoreBase

    from m8flow_backend.db import alembic_target_metadata

    alembic_target_metadata()  # registers every core model on CoreBase.metadata
    core_tables = set(CoreBase.metadata.tables)
    assert {"process_instance", "work_item", "task", "scheduler_job"} <= core_tables

    with admin_engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diffs = compare_metadata(context, CoreBase.metadata)

    found = set()
    unexplained = []
    for diff in diffs:
        for item in diff if isinstance(diff, list) else [diff]:
            signature = _signature(item)
            if signature is None:
                unexplained.append(repr(item))
                continue
            if signature[1] not in core_tables:
                continue  # host-owned tables are not described by core metadata
            if signature in KNOWN_DIFFERENCES:
                found.add(signature)
            else:
                unexplained.append(f"{signature}: {item!r}")

    assert unexplained == [], "core ORM and migrated schema differ:\n" + "\n".join(unexplained)
    # A known difference that disappears means the allowlist entry is stale.
    assert found == KNOWN_DIFFERENCES


def test_runtime_role_cannot_bypass_rls(migrated_database):
    """The suite's isolation claims rest on the host role being subject to RLS."""
    engine = sa.create_engine(migrated_database.runtime_uri)
    try:
        with engine.connect() as conn:
            superuser, bypass = conn.execute(
                sa.text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).one()
            rls_tables = set(
                conn.execute(sa.text("SELECT relname FROM pg_class WHERE relrowsecurity")).scalars()
            )
    finally:
        engine.dispose()
    assert (superuser, bypass) == (False, False)
    assert {"process_instance", "work_item", "work_item_user", "task", "scheduler_job", "json_data"} <= rls_tables
