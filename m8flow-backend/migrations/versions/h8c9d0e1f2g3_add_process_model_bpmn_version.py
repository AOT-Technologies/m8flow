"""add_process_model_bpmn_version

Revision ID: h8c9d0e1f2g3
Revises: e4f5a6b7c8d9
Create Date: 2026-04-23

Store BPMN XML snapshots per process model version so historical diagrams remain
accurate even after the underlying process model is edited.  Instances reference
the version via bpmn_version_id FK.
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
    # -- 1. Create the version table ------------------------------------------------
    op.create_table(
        "process_model_bpmn_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("process_model_identifier", sa.String(length=255), nullable=False),
        sa.Column("bpmn_xml_hash", sa.String(length=64), nullable=False),
        sa.Column("bpmn_xml_file_contents", sa.Text(), nullable=False),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["m8f_tenant_id"],
            ["m8flow_tenant.id"],
        ),
        sa.UniqueConstraint(
            "m8f_tenant_id",
            "process_model_identifier",
            "bpmn_xml_hash",
            name="uq_process_model_bpmn_version_tenant_model_hash",
        ),
    )
    op.create_index(
        "ix_process_model_bpmn_version_m8f_tenant_id",
        "process_model_bpmn_version",
        ["m8f_tenant_id"],
    )
    op.create_index(
        "ix_process_model_bpmn_version_process_model_identifier",
        "process_model_bpmn_version",
        ["process_model_identifier"],
    )
    op.create_index(
        "ix_process_model_bpmn_version_bpmn_xml_hash",
        "process_model_bpmn_version",
        ["bpmn_xml_hash"],
    )
    op.create_index(
        "ix_process_model_bpmn_version_created_at_in_seconds",
        "process_model_bpmn_version",
        ["created_at_in_seconds"],
    )

    # -- 2. Add FK column on process_instance ---------------------------------------
    op.add_column(
        "process_instance",
        sa.Column(
            "bpmn_version_id",
            sa.Integer(),
            sa.ForeignKey("process_model_bpmn_version.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_process_instance_bpmn_version_id",
        "process_instance",
        ["bpmn_version_id"],
    )

    # -- 3. RLS (PostgreSQL only) ---------------------------------------------------
    if _is_postgres():
        policy_name = "process_model_bpmn_version_tenant_isolation"
        op.execute(sa.text("ALTER TABLE process_model_bpmn_version ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON process_model_bpmn_version"))
        op.execute(
            sa.text(
                f"CREATE POLICY {policy_name} ON process_model_bpmn_version "
                "USING (m8f_tenant_id = current_setting('app.current_tenant', true)) "
                "WITH CHECK (m8f_tenant_id = current_setting('app.current_tenant', true))"
            )
        )


def downgrade() -> None:
    # -- RLS cleanup ----------------------------------------------------------------
    if _is_postgres():
        policy_name = "process_model_bpmn_version_tenant_isolation"
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON process_model_bpmn_version"))
        op.execute(sa.text("ALTER TABLE process_model_bpmn_version DISABLE ROW LEVEL SECURITY"))

    # -- Remove FK column from process_instance -------------------------------------
    op.drop_index("ix_process_instance_bpmn_version_id", table_name="process_instance")
    op.drop_column("process_instance", "bpmn_version_id")

    # -- Drop version table ---------------------------------------------------------
    op.drop_index("ix_process_model_bpmn_version_created_at_in_seconds", table_name="process_model_bpmn_version")
    op.drop_index("ix_process_model_bpmn_version_bpmn_xml_hash", table_name="process_model_bpmn_version")
    op.drop_index("ix_process_model_bpmn_version_process_model_identifier", table_name="process_model_bpmn_version")
    op.drop_index("ix_process_model_bpmn_version_m8f_tenant_id", table_name="process_model_bpmn_version")
    op.drop_table("process_model_bpmn_version")
