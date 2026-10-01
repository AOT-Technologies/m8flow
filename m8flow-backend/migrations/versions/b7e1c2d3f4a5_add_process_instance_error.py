"""Add m8flow_process_instance_error (service-task failure messages).

Core records a bare ``task_failed`` event with no message, so the Events tab and
the Process Error banner had nothing to show. The host now stores the text.

Databases created by the root revision already have this table -- it builds from
the live ORM metadata -- so the create is skipped there (same guard as
a1b2c3d4e5f6). The PostgreSQL row-level-security policy pair the root revision
puts on every tenant-scoped table is (re)applied either way, idempotently.

Revision ID: b7e1c2d3f4a5
Revises: f4254352d453
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7e1c2d3f4a5"
down_revision = "f4254352d453"
branch_labels = None
depends_on = None

TABLE_NAME = "m8flow_process_instance_error"

# Same names and predicates as the root revision's _enable_rls (1518b05122bc).
_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _table_exists() -> bool:
    return TABLE_NAME in sa.inspect(op.get_bind()).get_table_names()


def _enable_rls() -> None:
    """Tenant isolation + SELECT-only super-admin bypass. PostgreSQL only."""
    if op.get_bind().dialect.name != "postgresql":
        return
    tenant_policy = f"{TABLE_NAME}_tenant_isolation"
    bypass_policy = f"{TABLE_NAME}_super_admin_select"
    op.execute(sa.text(f"ALTER TABLE {TABLE_NAME} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {tenant_policy} ON {TABLE_NAME}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {tenant_policy} ON {TABLE_NAME} "
            f"FOR ALL USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
        )
    )
    op.execute(sa.text(f"DROP POLICY IF EXISTS {bypass_policy} ON {TABLE_NAME}"))
    op.execute(
        sa.text(f"CREATE POLICY {bypass_policy} ON {TABLE_NAME} FOR SELECT USING {_BYPASS_PREDICATE}")
    )


def _create_table() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
        sa.Column("process_instance_id", sa.Integer(), nullable=False),
        sa.Column("task_guid", sa.String(36), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
    )
    for column in ("m8f_tenant_id", "process_instance_id", "task_guid"):
        op.create_index(f"ix_host_{TABLE_NAME}_{column}", TABLE_NAME, [column])


def upgrade() -> None:
    if not _table_exists():
        _create_table()
    _enable_rls()


def downgrade() -> None:
    if not _table_exists():
        return
    op.drop_table(TABLE_NAME)
