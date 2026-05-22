"""Allow app-level super-admin RLS bypass via app.bypass_rls session setting (SELECT-only).

Revision ID: i2b3c4d5e6f7
Revises: h1a2b3c4d5e6
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "i2b3c4d5e6f7"
down_revision = "h1a2b3c4d5e6"
branch_labels = None
depends_on = None


_TENANT_ONLY_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_ONLY_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _tenant_tables() -> list[str]:
    """All tables in current schema that have an m8f_tenant_id column."""
    rows = op.get_bind().execute(
        sa.text(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND column_name = 'm8f_tenant_id'
            ORDER BY table_name
            """
        )
    ).fetchall()
    return [str(r[0]) for r in rows]


def _apply_policies(*, predicate_all: str, add_bypass_select: bool) -> None:
    for table in _tenant_tables():
        tenant_policy = f"{table}_tenant_isolation"
        super_admin_select_policy = f"{table}_super_admin_select"

        # Ensure RLS is on (safe if already enabled).
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))

        # Replace the tenant isolation policy to control write behavior.
        op.execute(sa.text(f"DROP POLICY IF EXISTS {tenant_policy} ON {table}"))
        op.execute(
            sa.text(
                f"CREATE POLICY {tenant_policy} ON {table} "
                f"FOR ALL USING {predicate_all} WITH CHECK {predicate_all}"
            )
        )

        # Super-admin read policy (bypass is SELECT-only).
        op.execute(sa.text(f"DROP POLICY IF EXISTS {super_admin_select_policy} ON {table}"))
        if add_bypass_select:
            op.execute(
                sa.text(
                    f"CREATE POLICY {super_admin_select_policy} ON {table} "
                    f"FOR SELECT USING {_BYPASS_ONLY_PREDICATE}"
                )
            )


def upgrade() -> None:
    if not _is_postgres():
        return
    # Strict tenant-only writes; bypass only for SELECT.
    _apply_policies(predicate_all=_TENANT_ONLY_PREDICATE, add_bypass_select=True)


def downgrade() -> None:
    if not _is_postgres():
        return
    # Restore pre-i2b3 behavior: tenant-only isolation, without bypass SELECT policy.
    _apply_policies(predicate_all=_TENANT_ONLY_PREDICATE, add_bypass_select=False)
