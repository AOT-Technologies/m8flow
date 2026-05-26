"""Add process model and process group soft-delete tracking tables.

Revision ID: j3c4d5e6f7a8
Revises: i2b3c4d5e6f7
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa

revision = "j3c4d5e6f7a8"
down_revision = "i2b3c4d5e6f7"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "m8flow_process_model_deletion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("original_identifier", sa.String(length=255), nullable=False),
        sa.Column("deleted_identifier", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("parent_group_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="SOFT_DELETED"),
        sa.Column("deleted_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("deleted_by", sa.String(length=255), nullable=False),
        sa.Column("restored_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("restored_by", sa.String(length=255), nullable=True),
        sa.Column("restored_identifier", sa.String(length=255), nullable=True),
        sa.Column("purged_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("notes", sa.JSON(), nullable=True),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
    )
    op.create_index("ix_pmd_m8f_tenant_id", "m8flow_process_model_deletion", ["m8f_tenant_id"])
    op.create_index("ix_pmd_original_identifier", "m8flow_process_model_deletion", ["original_identifier"])
    op.create_index("ix_pmd_status", "m8flow_process_model_deletion", ["status"])
    op.create_index("ix_pmd_deleted_at", "m8flow_process_model_deletion", ["deleted_at_in_seconds"])

    op.create_table(
        "m8flow_process_group_deletion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("original_identifier", sa.String(length=255), nullable=False),
        sa.Column("deleted_identifier", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("parent_group_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="SOFT_DELETED"),
        sa.Column("deleted_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("deleted_by", sa.String(length=255), nullable=False),
        sa.Column("restored_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("restored_by", sa.String(length=255), nullable=True),
        sa.Column("restored_identifier", sa.String(length=255), nullable=True),
        sa.Column("purged_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("notes", sa.JSON(), nullable=True),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
    )
    op.create_index("ix_pgd_m8f_tenant_id", "m8flow_process_group_deletion", ["m8f_tenant_id"])
    op.create_index("ix_pgd_original_identifier", "m8flow_process_group_deletion", ["original_identifier"])
    op.create_index("ix_pgd_status", "m8flow_process_group_deletion", ["status"])
    op.create_index("ix_pgd_deleted_at", "m8flow_process_group_deletion", ["deleted_at_in_seconds"])

    if _is_postgres():
        for table in ("m8flow_process_model_deletion", "m8flow_process_group_deletion"):
            policy_name = f"{table}_tenant_isolation"
            op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table}"))
            op.execute(
                sa.text(
                    f"CREATE POLICY {policy_name} ON {table} "
                    "USING (m8f_tenant_id = current_setting('app.current_tenant', true)) "
                    "WITH CHECK (m8f_tenant_id = current_setting('app.current_tenant', true))"
                )
            )


def downgrade() -> None:
    if _is_postgres():
        for table in ("m8flow_process_group_deletion", "m8flow_process_model_deletion"):
            policy_name = f"{table}_tenant_isolation"
            op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table}"))
            op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_pgd_deleted_at", table_name="m8flow_process_group_deletion")
    op.drop_index("ix_pgd_status", table_name="m8flow_process_group_deletion")
    op.drop_index("ix_pgd_original_identifier", table_name="m8flow_process_group_deletion")
    op.drop_index("ix_pgd_m8f_tenant_id", table_name="m8flow_process_group_deletion")
    op.drop_table("m8flow_process_group_deletion")

    op.drop_index("ix_pmd_deleted_at", table_name="m8flow_process_model_deletion")
    op.drop_index("ix_pmd_status", table_name="m8flow_process_model_deletion")
    op.drop_index("ix_pmd_original_identifier", table_name="m8flow_process_model_deletion")
    op.drop_index("ix_pmd_m8f_tenant_id", table_name="m8flow_process_model_deletion")
    op.drop_table("m8flow_process_model_deletion")
