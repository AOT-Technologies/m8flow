"""Add field-level connector configuration metadata.

The connector storage decision separates non-sensitive fields from sensitive
ones: only non-sensitive values may be stored in the database.  This revision
is deliberately additive.  ``config_json`` and ``secret_refs`` remain on the
parent profile until their data is migrated in a later cutover revision.

Revision ID: t3u4v5w6x7y8
Revises: s2l3m4n5o6p7
Create Date: 2026-08-28

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "t3u4v5w6x7y8"
down_revision = "s2l3m4n5o6p7"
branch_labels = None
depends_on = None

CONFIGURATION_TABLE = "m8flow_connector_configuration"
VARIABLE_TABLE = "m8flow_connector_variable"

_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade():
    # Existing configurations cannot gain a provider document or registry
    # schema version until the explicit backfill step, so both start nullable.
    with op.batch_alter_table(CONFIGURATION_TABLE, schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider_key", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("schema_version", sa.String(length=64), nullable=True))

    op.create_table(
        VARIABLE_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("connector_configuration_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=255), nullable=False),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False),
        sa.Column("value", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("is_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(is_sensitive = false) OR (value IS NULL)",
            name="ck_m8flow_connector_variable_sensitive_value",
        ),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
        sa.ForeignKeyConstraint(
            ["connector_configuration_id"],
            [f"{CONFIGURATION_TABLE}.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connector_configuration_id",
            "field_name",
            name="uq_m8flow_connector_variable_field",
        ),
    )
    with op.batch_alter_table(VARIABLE_TABLE, schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_m8flow_connector_variable_m8f_tenant_id"),
            ["m8f_tenant_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_m8flow_connector_variable_connector_configuration_id"),
            ["connector_configuration_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_m8flow_connector_variable_tenant_configuration",
            ["m8f_tenant_id", "connector_configuration_id"],
            unique=False,
        )

    if not _is_postgres():
        return

    op.execute(sa.text(f"ALTER TABLE {VARIABLE_TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {VARIABLE_TABLE}_tenant_isolation ON {VARIABLE_TABLE}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {VARIABLE_TABLE}_tenant_isolation ON {VARIABLE_TABLE} "
            f"FOR ALL USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
        )
    )
    op.execute(sa.text(f"DROP POLICY IF EXISTS {VARIABLE_TABLE}_super_admin_select ON {VARIABLE_TABLE}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {VARIABLE_TABLE}_super_admin_select ON {VARIABLE_TABLE} "
            f"FOR SELECT USING {_BYPASS_PREDICATE}"
        )
    )


def downgrade():
    if _is_postgres():
        op.execute(sa.text(f"DROP POLICY IF EXISTS {VARIABLE_TABLE}_super_admin_select ON {VARIABLE_TABLE}"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {VARIABLE_TABLE}_tenant_isolation ON {VARIABLE_TABLE}"))

    with op.batch_alter_table(VARIABLE_TABLE, schema=None) as batch_op:
        batch_op.drop_index("ix_m8flow_connector_variable_tenant_configuration")
        batch_op.drop_index(batch_op.f("ix_m8flow_connector_variable_connector_configuration_id"))
        batch_op.drop_index(batch_op.f("ix_m8flow_connector_variable_m8f_tenant_id"))
    op.drop_table(VARIABLE_TABLE)

    with op.batch_alter_table(CONFIGURATION_TABLE, schema=None) as batch_op:
        batch_op.drop_column("schema_version")
        batch_op.drop_column("provider_key")
