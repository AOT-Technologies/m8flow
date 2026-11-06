"""Add durable compensation journal.

Revision ID: fa8b9c0d1e2f
Revises: c1e4f5a6b7d8
"""

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


def _ownership_fk(table: str) -> str:
    return f"fk_{revision}_{table}_tenant"


def _tenant_index(table: str) -> str:
    return f"ix_{revision}_{table}_m8f_tenant_id"


def _owns_table(inspector: sa.Inspector, table: str) -> bool:
    return any(
        fk["name"] == _ownership_fk(table)
        and fk["constrained_columns"] == ["m8f_tenant_id"]
        and fk["referred_table"] == "m8flow_tenant"
        and fk["referred_columns"] == ["id"]
        for fk in inspector.get_foreign_keys(table)
    )


def _create_table(table: str, *columns) -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(table):
        # Fresh databases may already have the journal from the root migration.
        if not _owns_table(inspector, table):
            return
        existing_indexes = {index["name"] for index in inspector.get_indexes(table)}
    else:
        # Record ownership in CREATE TABLE, before either index can fail.
        op.create_table(
            table,
            *columns,
            sa.ForeignKeyConstraint(
                ["m8f_tenant_id"], ["m8flow_tenant.id"], name=_ownership_fk(table)
            ),
        )
        existing_indexes = set()

    for name, column in (
        (_tenant_index(table), "m8f_tenant_id"),
        (f"ix_{table}_process_instance_id", "process_instance_id"),
    ):
        if name not in existing_indexes:
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
    op.execute(sa.DDL(f"CREATE POLICY {bypass_policy} ON {table} FOR SELECT USING {bypass}"))


def upgrade() -> None:
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
    inspector = sa.inspect(op.get_bind())
    # Keep tables whose ownership cannot be established, including those from older builds.
    for table in reversed(TABLES):
        if inspector.has_table(table) and _owns_table(inspector, table):
            op.drop_table(table)
