"""add vault metadata table

Revision ID: q0r1s2t3u4v5
Revises: p9i0j1k2l3m4
Create Date: 2026-08-05 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "q0r1s2t3u4v5"
down_revision = "p9i0j1k2l3m4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vault_metadata",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("modified_by", sa.String(length=255), nullable=False),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("m8f_tenant_id", "name", name="uq_vault_metadata_tenant_name"),
    )
    op.create_index("ix_vault_metadata_tenant_name", "vault_metadata", ["m8f_tenant_id", "name"])
    op.create_index("ix_vault_metadata_user_id", "vault_metadata", ["user_id"])


def downgrade():
    op.drop_index("ix_vault_metadata_user_id", table_name="vault_metadata")
    op.drop_index("ix_vault_metadata_tenant_name", table_name="vault_metadata")
    op.drop_table("vault_metadata")
