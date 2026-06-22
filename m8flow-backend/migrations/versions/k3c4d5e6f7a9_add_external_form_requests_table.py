"""Add m8flow_external_form_requests table

Single consolidated migration for the external-form tracking table. Final schema:
external_form_url is TEXT (the link can embed a full form schema), notified_at_in_seconds
+ the sweep index are included, and there is no last_error column (failure reasons are
logged by the notification worker / backend instead of stored).

Revision ID: k3c4d5e6f7a9
Revises: j2b3c4d5e6f8
Create Date: 2026-06-10 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "k3c4d5e6f7a9"
down_revision = "j2b3c4d5e6f8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "m8flow_external_form_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("reference_id", sa.String(length=255), nullable=False),
        sa.Column("process_instance_id", sa.Integer(), nullable=False),
        sa.Column("task_guid", sa.String(length=36), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("user_details", sa.JSON(), nullable=True),
        sa.Column("external_form_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("form_submission_data", sa.JSON(), nullable=True),
        sa.Column("expires_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("notified_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("m8flow_external_form_requests", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_m8flow_external_form_requests_m8f_tenant_id"), ["m8f_tenant_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_m8flow_external_form_requests_reference_id"), ["reference_id"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_m8flow_external_form_requests_recipient_user_id"), ["recipient_user_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_m8flow_external_form_requests_status"), ["status"], unique=False)
        batch_op.create_index(
            "ix_m8flow_external_form_requests_instance_task", ["process_instance_id", "task_guid"], unique=False
        )
        batch_op.create_index(
            "ix_m8flow_external_form_requests_sweep", ["status", "notified_at_in_seconds"], unique=False
        )


def downgrade():
    with op.batch_alter_table("m8flow_external_form_requests", schema=None) as batch_op:
        batch_op.drop_index("ix_m8flow_external_form_requests_sweep")
        batch_op.drop_index("ix_m8flow_external_form_requests_instance_task")
        batch_op.drop_index(batch_op.f("ix_m8flow_external_form_requests_status"))
        batch_op.drop_index(batch_op.f("ix_m8flow_external_form_requests_recipient_user_id"))
        batch_op.drop_index(batch_op.f("ix_m8flow_external_form_requests_reference_id"))
        batch_op.drop_index(batch_op.f("ix_m8flow_external_form_requests_m8f_tenant_id"))
    op.drop_table("m8flow_external_form_requests")
