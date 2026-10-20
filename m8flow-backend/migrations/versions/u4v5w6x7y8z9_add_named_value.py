"""Add tenant-scoped reusable non-sensitive named values.

Revision ID: u4v5w6x7y8z9
Revises: t3u4v5w6x7y8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "u4v5w6x7y8z9"
down_revision = "t3u4v5w6x7y8"
branch_labels = None
depends_on = None

TABLE = "m8flow_named_value"
TENANT_POLICY = f"{TABLE}_tenant_isolation"
BYPASS_POLICY = f"{TABLE}_super_admin_select"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("value", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("is_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "m8f_tenant_id", "name", name="uq_m8flow_named_value_tenant_name"
        ),
        sa.CheckConstraint(
            "(is_sensitive = false AND value IS NOT NULL) OR "
            "(is_sensitive = true AND value IS NULL) OR "
            "(is_configured = false AND value IS NULL)",
            name="ck_m8flow_named_value_storage",
        ),
    )
    op.create_index("ix_m8flow_named_value_tenant", TABLE, ["m8f_tenant_id"])

    if _is_postgres():
        predicate = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
        bypass = "(current_setting('app.bypass_rls', true) = 'on')"
        op.execute(sa.text(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {TENANT_POLICY} ON {TABLE} FOR ALL "
                f"USING {predicate} WITH CHECK {predicate}"
            )
        )
        op.execute(
            sa.text(
                f"CREATE POLICY {BYPASS_POLICY} ON {TABLE} FOR SELECT USING {bypass}"
            )
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute(sa.text(f"DROP POLICY IF EXISTS {BYPASS_POLICY} ON {TABLE}"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TENANT_POLICY} ON {TABLE}"))
    op.drop_index("ix_m8flow_named_value_tenant", table_name=TABLE)
    op.drop_table(TABLE)
