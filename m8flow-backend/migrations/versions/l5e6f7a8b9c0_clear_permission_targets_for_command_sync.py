"""Clear permission targets so login-time sync can repopulate command-aware rows.

Revision ID: l5e6f7a8b9c0
Revises: k4d5e6f7a8b9
Create Date: 2026-06-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "l5e6f7a8b9c0"
down_revision = "k4d5e6f7a8b9"
branch_labels = None
depends_on = None

PERMISSION_ASSIGNMENT_TABLE = "permission_assignment"
PERMISSION_TARGET_TABLE = "permission_target"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    connection = op.get_bind()

    if _table_exists(PERMISSION_ASSIGNMENT_TABLE):
        connection.execute(sa.text(f'DELETE FROM "{PERMISSION_ASSIGNMENT_TABLE}"'))

    if _table_exists(PERMISSION_TARGET_TABLE):
        connection.execute(sa.text(f'DELETE FROM "{PERMISSION_TARGET_TABLE}"'))


def downgrade() -> None:
    # Irreversible data cleanup: login-time permission sync repopulates these rows.
    return None
