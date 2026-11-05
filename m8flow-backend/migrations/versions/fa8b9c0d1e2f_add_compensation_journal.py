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
            sa.ForeignKey("m8flow_tenant.id"),
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


def _create_table(table: str, *columns) -> None:
    # Fresh databases may already have the journal from the root migration.
    if sa.inspect(op.get_bind()).has_table(table):
        return
    op.create_table(table, *columns)
    for column in ("m8f_tenant_id", "process_instance_id"):
        op.create_index(f"ix_{table}_{column}", table, [column])


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
    for table in ("compensation_record", "compensation_run", "compensation_scope"):
        op.drop_table(table)
