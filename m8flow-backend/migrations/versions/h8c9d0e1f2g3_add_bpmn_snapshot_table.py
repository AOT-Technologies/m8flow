"""add_bpmn_snapshot_table

Revision ID: h8c9d0e1f2g3
Revises: e4f5a6b7c8d9
Create Date: 2026-04-21

Store BPMN XML snapshots per process instance so historical diagrams remain accurate
even after the underlying process model is edited.
"""

from alembic import op
import sqlalchemy as sa


revision = "h8c9d0e1f2g3"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "process_instance_bpmn_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("process_instance_id", sa.Integer(), nullable=False),
        sa.Column("bpmn_xml_file_contents", sa.Text(), nullable=False),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["m8f_tenant_id"],
            ["m8flow_tenant.id"],
        ),
        sa.ForeignKeyConstraint(
            ["process_instance_id"],
            ["process_instance.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("process_instance_id", name="uq_process_instance_bpmn_snapshot_instance_id"),
    )
    op.create_index(
        "ix_process_instance_bpmn_snapshot_m8f_tenant_id",
        "process_instance_bpmn_snapshot",
        ["m8f_tenant_id"],
    )
    op.create_index(
        "ix_process_instance_bpmn_snapshot_process_instance_id",
        "process_instance_bpmn_snapshot",
        ["process_instance_id"],
    )
    op.create_index(
        "ix_process_instance_bpmn_snapshot_created_at_in_seconds",
        "process_instance_bpmn_snapshot",
        ["created_at_in_seconds"],
    )

    if _is_postgres():
        policy_name = "process_instance_bpmn_snapshot_tenant_isolation"
        op.execute(sa.text("ALTER TABLE process_instance_bpmn_snapshot ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON process_instance_bpmn_snapshot"))
        op.execute(
            sa.text(
                f"CREATE POLICY {policy_name} ON process_instance_bpmn_snapshot "
                "USING (m8f_tenant_id = current_setting('app.current_tenant', true)) "
                "WITH CHECK (m8f_tenant_id = current_setting('app.current_tenant', true))"
            )
        )


def downgrade() -> None:
    if _is_postgres():
        policy_name = "process_instance_bpmn_snapshot_tenant_isolation"
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON process_instance_bpmn_snapshot"))
        op.execute(sa.text("ALTER TABLE process_instance_bpmn_snapshot DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_process_instance_bpmn_snapshot_created_at_in_seconds", table_name="process_instance_bpmn_snapshot")
    op.drop_index("ix_process_instance_bpmn_snapshot_process_instance_id", table_name="process_instance_bpmn_snapshot")
    op.drop_index("ix_process_instance_bpmn_snapshot_m8f_tenant_id", table_name="process_instance_bpmn_snapshot")
    op.drop_table("process_instance_bpmn_snapshot")

