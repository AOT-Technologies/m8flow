"""add_process_model_template: track template provenance for process models

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-02-11

"""
from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "m8flow_process_model_template",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("process_model_identifier", sa.String(length=255), nullable=False, unique=True),
        sa.Column("source_template_id", sa.Integer(), sa.ForeignKey("m8flow_templates.id"), nullable=False),
        sa.Column("source_template_key", sa.String(length=255), nullable=False),
        sa.Column("source_template_version", sa.String(length=50), nullable=False),
        sa.Column("source_template_name", sa.String(length=255), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), sa.ForeignKey("m8flow_tenant.id"), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
    )
    op.create_index("ix_pmt_process_model_identifier", "m8flow_process_model_template", ["process_model_identifier"], unique=False)
    op.create_index("ix_pmt_source_template_id", "m8flow_process_model_template", ["source_template_id"], unique=False)
    op.create_index("ix_pmt_source_template_key", "m8flow_process_model_template", ["source_template_key"], unique=False)
    op.create_index("ix_pmt_m8f_tenant_id", "m8flow_process_model_template", ["m8f_tenant_id"], unique=False)


def downgrade():
    op.drop_index("ix_pmt_m8f_tenant_id", table_name="m8flow_process_model_template")
    op.drop_index("ix_pmt_source_template_key", table_name="m8flow_process_model_template")
    op.drop_index("ix_pmt_source_template_id", table_name="m8flow_process_model_template")
    op.drop_index("ix_pmt_process_model_identifier", table_name="m8flow_process_model_template")
    op.drop_table("m8flow_process_model_template")
