"""Add durable compensation journal.

Revision ID: fa8b9c0d1e2f
Revises: c1e4f5a6b7d8
"""

import logging
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import SchemaItem

LOGGER = logging.getLogger("alembic.runtime.migration")

revision = "fa8b9c0d1e2f"
down_revision = "c1e4f5a6b7d8"
branch_labels = None
depends_on = None


def _common(table: str) -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "m8f_tenant_id",
            sa.String(255),
            sa.ForeignKey("m8flow_tenant.id", name=_ownership_fk(table)),
            nullable=False,
        ),
        sa.Column(
            "process_instance_id",
            sa.Integer(),
            sa.ForeignKey("process_instance.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


# No FKs between journal tables, on purpose. Core owns and writes these rows, and the
# schema must match core's ORM (tests/integration/test_schema_matches_core.py).
# scope_id/run_id are core's logical UUIDs. run_id is not unique in compensation_run,
# and a compensable activity's record can be written before its enclosing scope
# completes, so host-only FKs could reject valid core writes. Integrity here comes from
# the FKs to process_instance and m8flow_tenant, the per-instance *_occurrence and
# *_sequence unique constraints, tenant RLS, and workflow.delete_instance clearing
# record -> run -> scope. Sibling FKs must be added to core's ORM first.
TABLES = ("compensation_scope", "compensation_run", "compensation_record")
_OWNERSHIP = sa.table(
    f"m8flow_{revision}_journal_ownership",
    sa.column("table_name", sa.String(63)),
    sa.column("creation_marker", sa.String(63)),
)


def _ownership_fk(table: str) -> str:
    return f"fk_{revision}_{table}_tenant"


def _tenant_index(table: str) -> str:
    return f"ix_{revision}_{table}_m8f_tenant_id"


def _owns_table(bind: sa.Connection, table: str, creation_marker: str) -> bool:
    # Fresh inspector per check: Inspector caches reflection, so never reuse one across DDL.
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    # A stale ownership row cannot authorize dropping a replacement table.
    if not any(check["name"] == creation_marker for check in inspector.get_check_constraints(table)):
        return False
    return any(
        fk["name"] == _ownership_fk(table)
        and fk["constrained_columns"] == ["m8f_tenant_id"]
        and fk["referred_table"] == "m8flow_tenant"
        and fk["referred_columns"] == ["id"]
        for fk in inspector.get_foreign_keys(table)
    )


def _sqlite_index_name(bind: sa.Connection, preferred: str) -> str:
    # SQLite index names share the schema namespace with other tables' indexes.
    occupied = {name.casefold() for name in bind.scalars(sa.text("SELECT name FROM main.sqlite_master"))}
    candidate = preferred
    suffix = 2
    while candidate.casefold() in occupied:
        candidate = f"{preferred}_{suffix}"
        suffix += 1
    return candidate


def _validate_existing_table(inspector: sa.Inspector, expected: sa.Table) -> None:
    table = expected.name
    bind = inspector.bind
    columns = {column["name"]: column for column in inspector.get_columns(table)}
    problems = []
    expected_names = set(expected.c.keys())
    if missing := expected_names - columns.keys():
        problems.append(f"missing columns: {', '.join(sorted(missing))}")
    if extra := columns.keys() - expected_names:
        problems.append(f"unexpected columns: {', '.join(sorted(extra))}")

    has_id_pk = inspector.get_pk_constraint(table)["constrained_columns"] == ["id"]
    if not has_id_pk:
        problems.append("expected a primary key on (id)")
    # SQLite creates a separate PK index when id is not a rowid alias.
    sqlite_rowid = has_id_pk and bind.dialect.name == "sqlite" and not bind.scalar(
        sa.text("SELECT 1 FROM pragma_index_list(:table_name) WHERE origin = 'pk'"),
        {"table_name": table},
    )
    if has_id_pk and not (sqlite_rowid or columns["id"].get("autoincrement")):
        problems.append("id must be generated automatically")

    for column in expected.columns:
        actual = columns.get(column.name)
        if actual is None:
            continue
        actual_type = actual["type"].compile(dialect=bind.dialect)
        expected_type = column.type.compile(dialect=bind.dialect)
        if actual_type != expected_type:
            problems.append(f"{column.name} has type {actual_type}, expected {expected_type}")
        # SQLite can reflect a rowid alias as nullable even though it cannot store NULL.
        if actual["nullable"] != column.nullable and not (column.name == "id" and sqlite_rowid):
            problems.append(f"{column.name} must be {'nullable' if column.nullable else 'NOT NULL'}")

    expected_unique = {
        frozenset(constraint.columns.keys())
        for constraint in expected.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    actual_unique = {
        frozenset(constraint["column_names"]) for constraint in inspector.get_unique_constraints(table)
    }
    if actual_unique != expected_unique:
        required = sorted(", ".join(sorted(columns)) for columns in expected_unique)
        problems.append(f"expected unique constraints on ({'), ('.join(required)})")

    expected_fks = {
        tuple((element.parent.name, element.target_fullname) for element in constraint.elements)
        for constraint in expected.foreign_key_constraints
    }
    actual_fks = set()
    for constraint in inspector.get_foreign_keys(table):
        schema = constraint.get("referred_schema")
        target = constraint["referred_table"]
        if schema and schema != inspector.default_schema_name:
            target = f"{schema}.{target}"
        actual_fks.add(tuple(
            (column, f"{target}.{referred_column}")
            for column, referred_column in zip(
                constraint["constrained_columns"], constraint["referred_columns"], strict=True
            )
        ))
    if actual_fks != expected_fks:
        required = sorted(f"{column} references {target}" for key in expected_fks for column, target in key)
        problems.append(f"expected foreign keys: {', '.join(required)}")

    if problems:
        raise RuntimeError(
            f"Cannot adopt existing table {table!r}. {'; '.join(problems)}. "
            "Back up and rename the table, then rerun the migration."
        )


def _create_table(table: str, columns: list[SchemaItem]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(table):
        existing_indexes = inspector.get_indexes(table)
    else:
        creation_marker = f"ck_{revision}_{uuid4().hex}"
        # Start SQLite's write transaction before CREATE TABLE so the table and
        # ownership row are committed together, even with legacy sqlite3 mode.
        bind.execute(_OWNERSHIP.delete().where(_OWNERSHIP.c.table_name == table))
        op.create_table(
            table,
            *columns,
            sa.CheckConstraint("id IS NOT NULL", name=creation_marker),
        )
        bind.execute(_OWNERSHIP.insert().values(table_name=table, creation_marker=creation_marker))
        existing_indexes = []

    for name, column in (
        (_tenant_index(table), "m8f_tenant_id"),
        (f"ix_{table}_process_instance_id", "process_instance_id"),
    ):
        if any(
            index["column_names"] == [column]
            and not any(key.endswith("_where") for key in index.get("dialect_options", {}))
            for index in existing_indexes
        ):
            continue
        if bind.dialect.name == "sqlite":
            name = _sqlite_index_name(bind, name)
        elif any(index["name"] == name for index in existing_indexes):
            continue
        op.create_index(name, table, [column])


def _enable_rls(table: str) -> None:
    tenant_policy = f"{table}_tenant_isolation"
    bypass_policy = f"{table}_super_admin_select"
    tenant = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
    bypass = "(current_setting('app.bypass_rls', true) = 'on')"
    op.execute(sa.DDL(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {tenant_policy} ON {table}"))
    op.execute(sa.DDL(f"CREATE POLICY {tenant_policy} ON {table} FOR ALL USING {tenant} WITH CHECK {tenant}"))
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {bypass_policy} ON {table}"))
    # Bypass is SELECT-only by design (see m8flow_backend/docs/rls_notes.md): super-admin
    # stays read-only across tenants; writes still require app.current_tenant.
    op.execute(sa.DDL(f"CREATE POLICY {bypass_policy} ON {table} FOR SELECT USING {bypass}"))


def _journal_definitions() -> dict[str, list[SchemaItem]]:
    return {
        "compensation_scope": [
            *_common("compensation_scope"),
            sa.Column("scope_id", sa.String(36), nullable=False),
            sa.Column("parent_scope_id", sa.String(36)),
            sa.Column("activity_id", sa.String(255), nullable=False),
            sa.Column("completed", sa.Boolean(), nullable=False),
            sa.Column("data_hash", sa.String(255), nullable=False),
            sa.UniqueConstraint(
                "m8f_tenant_id",
                "process_instance_id",
                "scope_id",
                name="m8f_compensation_scope_occurrence",
            ),
        ],
        "compensation_run": [
            *_common("compensation_run"),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column("throw_task_guid", sa.String(36), nullable=False),
            sa.Column("scope_id", sa.String(36), nullable=False),
            sa.Column("wait_for_completion", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.UniqueConstraint(
                "m8f_tenant_id",
                "process_instance_id",
                "throw_task_guid",
                name="m8f_compensation_run_occurrence",
            ),
        ],
        "compensation_record": [
            *_common("compensation_record"),
            sa.Column("source_task_guid", sa.String(36), nullable=False),
            sa.Column("activity_id", sa.String(255), nullable=False),
            sa.Column("scope_id", sa.String(36), nullable=False),
            sa.Column("completion_sequence", sa.Integer(), nullable=False),
            sa.Column("handler_id", sa.String(255)),
            sa.Column("handler_task_guid", sa.String(36)),
            sa.Column("run_id", sa.String(36)),
            sa.Column("throw_task_guid", sa.String(36)),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("failure_details", sa.Text()),
            sa.Column("data_hash", sa.String(255), nullable=False),
            sa.Column("workflow_state_hash", sa.String(255)),
            sa.UniqueConstraint(
                "m8f_tenant_id",
                "process_instance_id",
                "source_task_guid",
                name="m8f_compensation_record_occurrence",
            ),
            sa.UniqueConstraint(
                "m8f_tenant_id",
                "process_instance_id",
                "completion_sequence",
                name="m8f_compensation_record_sequence",
            ),
        ],
    }


def upgrade() -> None:
    bind = op.get_bind()
    definitions = _journal_definitions()
    inspector = sa.inspect(bind)
    for name, items in definitions.items():
        if inspector.has_table(name):
            _validate_existing_table(inspector, sa.Table(name, sa.MetaData(), *items))

    if not inspector.has_table(_OWNERSHIP.name):
        if bind.dialect.name == "sqlite":
            # Legacy sqlite3 autocommits DDL until a write opens the transaction; open it
            # first so a failed upgrade also rolls back the ownership table.
            bind.execute(sa.text("UPDATE m8flow_tenant SET id = id WHERE 1 = 0"))
        op.create_table(
            _OWNERSHIP.name,
            sa.Column("table_name", sa.String(63), primary_key=True),
            sa.Column("creation_marker", sa.String(63), nullable=False),
        )
        # Self-row: downgrade only drops the ownership table if this revision created it.
        bind.execute(_OWNERSHIP.insert().values(table_name=_OWNERSHIP.name, creation_marker=revision))
    for name, items in definitions.items():
        _create_table(name, items)
    if bind.dialect.name == "postgresql":
        for table in TABLES:
            _enable_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_OWNERSHIP.name):
        return
    markers = dict(bind.execute(sa.select(_OWNERSHIP)).tuples().all())
    # Indexes added to pre-existing tables remain usable after downgrade.
    for table in reversed(TABLES):
        creation_marker = markers.get(table)
        if not creation_marker:
            continue
        if _owns_table(bind, table, creation_marker):
            op.drop_table(table)
            bind.execute(_OWNERSHIP.delete().where(_OWNERSHIP.c.table_name == table))
        else:
            LOGGER.warning(
                "Leaving %s in place: recorded as created by %s but now missing or replaced.", table, revision
            )
    if markers.get(_OWNERSHIP.name):
        op.drop_table(_OWNERSHIP.name)
