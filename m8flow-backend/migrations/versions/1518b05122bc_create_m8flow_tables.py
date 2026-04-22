from alembic import op
import sqlalchemy as sa

revision = "1518b05122bc"
down_revision = None

def upgrade():
    op.create_table(
        "m8flow_tenant",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

def downgrade():
    op.drop_table("m8flow_tenant")