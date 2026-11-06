"""Add durable compensation journal.

Revision ID: fa8b9c0d1e2f
Revises: c1e4f5a6b7d8
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "fa8b9c0d1e2f"
down_revision = "c1e4f5a6b7d8"
branch_labels = None
depends_on = None


def _common() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "m8f_tenant_id",
            sa.String(255),
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


def _owns_table(inspector: sa.Inspector, table: str, creation_marker: str) -> bool:
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


def _create_table(table: str, *columns) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(table):
        if not {"m8f_tenant_id", "process_instance_id"} <= {
            column["name"] for column in inspector.get_columns(table)
        }:
            return
        existing_indexes = inspector.get_indexes(table)
    else:
        creation_marker = f"ck_{revision}_{uuid4().hex}"
        # Start SQLite's write transaction before CREATE TABLE so the table and
        # ownership row are committed together, even with legacy sqlite3 mode.
        bind.execute(_OWNERSHIP.delete().where(_OWNERSHIP.c.table_name == table))
        op.create_table(
            table,
            *columns,
            sa.ForeignKeyConstraint(
                ["m8f_tenant_id"], ["m8flow_tenant.id"], name=_ownership_fk(table)
            ),
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


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table(_OWNERSHIP.name):
        op.create_table(
            _OWNERSHIP.name,
            sa.Column("table_name", sa.String(63), primary_key=True),
            sa.Column("creation_marker", sa.String(63), nullable=False),
        )
        # Self-row: downgrade only drops the ownership table if this revision created it.
        op.get_bind().execute(_OWNERSHIP.insert().values(table_name=_OWNERSHIP.name, creation_marker=revision))
    _create_table(
        "compensation_scope",
        *_common(),
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
    )
    _create_table(
        "compensation_run",
        *_common(),
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
    )
    _create_table(
        "compensation_record",
        *_common(),
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
    )
    if op.get_bind().dialect.name == "postgresql":
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
        inspector = sa.inspect(bind)
        if creation_marker and inspector.has_table(table) and _owns_table(inspector, table, creation_marker):
            op.drop_table(table)
            bind.execute(_OWNERSHIP.delete().where(_OWNERSHIP.c.table_name == table))
    if markers.get(_OWNERSHIP.name):
        op.drop_table(_OWNERSHIP.name)
