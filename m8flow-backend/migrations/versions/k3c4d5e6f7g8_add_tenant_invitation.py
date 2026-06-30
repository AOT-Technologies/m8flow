"""add tenant invitation table

Revision ID: k3c4d5e6f7g8
Revises: j2b3c4d5e6f8
Create Date: 2026-06-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "k3c4d5e6f7g8"
down_revision = "j2b3c4d5e6f8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "m8flow_tenant_invitation",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("roles", sa.String(length=1024), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "ACCEPTED",
                "REVOKED",
                "EXPIRED",
                name="tenantinvitationstatus",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("expires_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("accepted_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("modified_by", sa.String(length=255), nullable=False),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_m8flow_tenant_invitation_token_hash"),
    )
    op.create_index(
        "ix_m8flow_tenant_invitation_tenant_id",
        "m8flow_tenant_invitation",
        ["m8f_tenant_id"],
    )
    op.create_index(
        "ix_m8flow_tenant_invitation_email",
        "m8flow_tenant_invitation",
        ["email"],
    )
    op.create_index(
        "ix_m8flow_tenant_invitation_token_hash",
        "m8flow_tenant_invitation",
        ["token_hash"],
    )


def downgrade():
    op.drop_index(
        "ix_m8flow_tenant_invitation_token_hash",
        table_name="m8flow_tenant_invitation",
    )
    op.drop_index(
        "ix_m8flow_tenant_invitation_email",
        table_name="m8flow_tenant_invitation",
    )
    op.drop_index(
        "ix_m8flow_tenant_invitation_tenant_id",
        table_name="m8flow_tenant_invitation",
    )
    op.drop_table("m8flow_tenant_invitation")
    op.execute("DROP TYPE IF EXISTS tenantinvitationstatus")
