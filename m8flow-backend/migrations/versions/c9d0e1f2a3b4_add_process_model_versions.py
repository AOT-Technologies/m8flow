"""Add m8flow_process_model_version (published process-model snapshots).

Saving a published model now changes only its working copy on disk; Start runs
the newest row here until Publish changes snapshots the working copy again.

Databases created by the root revision build from the live ORM metadata, so the
create is skipped when the table already exists (same guard as b7e1c2d3f4a5).
The PostgreSQL row-level-security policy pair is (re)applied either way.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None

TABLE_NAME = "m8flow_process_model_version"

# Same names and predicates as the root revision's _enable_rls (1518b05122bc).
_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE_NAME)


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
        sa.Column("process_model_identifier", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("primary_file_name", sa.String(255), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("published_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=f"pk_host_{TABLE_NAME}"),
        sa.UniqueConstraint(
            "m8f_tenant_id",
            "process_model_identifier",
            "version",
            name="uq_process_model_version_tenant",
        ),
    )
    for column in ("m8f_tenant_id", "process_model_identifier"):
        op.create_index(f"ix_host_{TABLE_NAME}_{column}", TABLE_NAME, [column])


def upgrade() -> None:
    if not _table_exists():
        _create_table()
    _enable_rls()


def downgrade() -> None:
    if not _table_exists():
        return
    op.drop_table(TABLE_NAME)
