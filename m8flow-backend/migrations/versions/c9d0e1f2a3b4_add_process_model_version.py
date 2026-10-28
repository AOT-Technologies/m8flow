"""Add m8flow_process_model_version (process model save/publish/revert history).

Versioned publishing: the files on disk are the working copy, and Start runs
the newest `publish` / `baseline` row recorded here, so saving a published
model no longer changes what Start runs until Publish Changes.

Databases created by the root revision already have this table -- it builds
from the live ORM metadata -- so the create is skipped there (same guard as
b7e1c2d3f4a5). The PostgreSQL row-level-security policy pair is (re)applied
either way, idempotently.

Revision ID: c9d0e1f2a3b4
Revises: a8c1e2f3b4d5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c9d0e1f2a3b4"
down_revision = "a8c1e2f3b4d5"
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
    op.execute(sa.DDL(f"ALTER TABLE {TABLE_NAME} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {tenant_policy} ON {TABLE_NAME}"))
    op.execute(
        sa.DDL(
            f"CREATE POLICY {tenant_policy} ON {TABLE_NAME} "
            f"FOR ALL USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
        )
    )
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {bypass_policy} ON {TABLE_NAME}"))
    op.execute(
        sa.DDL(
            f"CREATE POLICY {bypass_policy} ON {TABLE_NAME} FOR SELECT USING {_BYPASS_PREDICATE}"
        )
    )


def _create_table() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
        sa.Column("process_model_identifier", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("primary_file_name", sa.String(255), nullable=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("reverted_from_version", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "m8f_tenant_id",
            "process_model_identifier",
            "version",
            name="uq_process_model_version_tenant_model_version",
        ),
    )
    for column in ("m8f_tenant_id", "process_model_identifier"):
        op.create_index(f"ix_host_{TABLE_NAME}_{column}", TABLE_NAME, [column])


def upgrade() -> None:
    if not _table_exists():
        _create_table()
    _enable_rls()


def downgrade() -> None:
    # Dropping the table drops its indexes and RLS policies with it.
    if not _table_exists():
        return
    op.drop_table(TABLE_NAME)
