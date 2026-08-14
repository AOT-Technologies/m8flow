"""Add m8flow_connector_configuration (named connector profiles)

One row per tenant/connector/profile. Non-sensitive values live in
config_json; sensitive ones live in the secret store and only their keys are
recorded in secret_refs, so this table never holds ciphertext.

Row Level Security matches the policy pair every other tenant table carries
after i2b3c4d5e6f7: tenant-only for all statements, plus a SELECT-only
super-admin bypass driven by the app.bypass_rls session setting.

Revision ID: q1r2s3t4u5v6
Revises: p9i0j1k2l3m4
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "q1r2s3t4u5v6"
down_revision = "p9i0j1k2l3m4"
branch_labels = None
depends_on = None

TABLE = "m8flow_connector_configuration"

_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("connector_type", sa.String(length=50), nullable=False),
        sa.Column("profile_name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("secret_refs", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "m8f_tenant_id",
            "connector_type",
            "profile_name",
            name="uq_m8flow_connector_configuration_profile",
        ),
    )
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_m8flow_connector_configuration_m8f_tenant_id"),
            ["m8f_tenant_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_m8flow_connector_configuration_tenant_type",
            ["m8f_tenant_id", "connector_type"],
            unique=False,
        )
        batch_op.create_index(
            "ix_m8flow_connector_configuration_tenant_active",
            ["m8f_tenant_id", "is_active"],
            unique=False,
        )

    if not _is_postgres():
        return

    # At most one default profile per (tenant, connector type).
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_m8flow_connector_configuration_default "
            f"ON {TABLE} (m8f_tenant_id, connector_type) WHERE is_default"
        )
    )

    op.execute(sa.text(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_tenant_isolation ON {TABLE}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {TABLE}_tenant_isolation ON {TABLE} "
            f"FOR ALL USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
        )
    )
    op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_super_admin_select ON {TABLE}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {TABLE}_super_admin_select ON {TABLE} "
            f"FOR SELECT USING {_BYPASS_PREDICATE}"
        )
    )


def downgrade():
    if _is_postgres():
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_super_admin_select ON {TABLE}"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_tenant_isolation ON {TABLE}"))
        op.execute(sa.text("DROP INDEX IF EXISTS uq_m8flow_connector_configuration_default"))

    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        batch_op.drop_index("ix_m8flow_connector_configuration_tenant_active")
        batch_op.drop_index("ix_m8flow_connector_configuration_tenant_type")
        batch_op.drop_index(batch_op.f("ix_m8flow_connector_configuration_m8f_tenant_id"))
    op.drop_table(TABLE)
