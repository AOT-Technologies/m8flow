"""Add notified_at_in_seconds to m8flow_external_form_requests (M8F-339)

Revision ID: l4d5e6f7a8b1
Revises: k3c4d5e6f7a9
Create Date: 2026-06-12 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "l4d5e6f7a8b1"
down_revision = "k3c4d5e6f7a9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("m8flow_external_form_requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notified_at_in_seconds", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_m8flow_external_form_requests_sweep", ["status", "notified_at_in_seconds"], unique=False
        )


def downgrade():
    with op.batch_alter_table("m8flow_external_form_requests", schema=None) as batch_op:
        batch_op.drop_index("ix_m8flow_external_form_requests_sweep")
        batch_op.drop_column("notified_at_in_seconds")
