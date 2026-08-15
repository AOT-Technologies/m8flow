"""Add generic audit_log table for Vault and future application audit events.

Revision ID: q1r2s3t4u5v6
Revises: p9i0j1k2l3m4
Create Date: 2026-08-14 11:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "q1r2s3t4u5v6"
down_revision = "p9i0j1k2l3m4"
branch_labels = None
depends_on = None

AUDIT_LOG_TABLE = "audit_log"


def upgrade():
    op.create_table(
        AUDIT_LOG_TABLE,
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default=sa.text("'info'")),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=True),
        sa.Column("actor_type", sa.String(length=64), nullable=True),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("actor_username", sa.String(length=255), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("resource_name", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table(AUDIT_LOG_TABLE, schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_log_category"), ["category"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_log_correlation_id"), ["correlation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_log_event_type"), ["event_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_log_m8f_tenant_id"), ["m8f_tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_log_request_id"), ["request_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_log_status"), ["status"], unique=False)
        batch_op.create_index("ix_audit_log_category_created_at", ["category", "created_at_in_seconds"], unique=False)
        batch_op.create_index("ix_audit_log_tenant_created_at", ["m8f_tenant_id", "created_at_in_seconds"], unique=False)

    with op.batch_alter_table(AUDIT_LOG_TABLE, schema=None) as batch_op:
        batch_op.alter_column("severity", server_default=None)


def downgrade():
    with op.batch_alter_table(AUDIT_LOG_TABLE, schema=None) as batch_op:
        batch_op.drop_index("ix_audit_log_tenant_created_at")
        batch_op.drop_index("ix_audit_log_category_created_at")
        batch_op.drop_index(batch_op.f("ix_audit_log_status"))
        batch_op.drop_index(batch_op.f("ix_audit_log_request_id"))
        batch_op.drop_index(batch_op.f("ix_audit_log_m8f_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_audit_log_event_type"))
        batch_op.drop_index(batch_op.f("ix_audit_log_correlation_id"))
        batch_op.drop_index(batch_op.f("ix_audit_log_category"))

    op.drop_table(AUDIT_LOG_TABLE)
