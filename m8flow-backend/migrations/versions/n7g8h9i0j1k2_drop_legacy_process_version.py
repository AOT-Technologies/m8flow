"""Drop legacy process_version from process_instance.

Revision ID: n7g8h9i0j1k2
Revises: m6f7a8b9c0d1
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "n7g8h9i0j1k2"
down_revision = "m6f7a8b9c0d1"
branch_labels = None
depends_on = None

PROCESS_INSTANCE_TABLE = "process_instance"
PROCESS_VERSION_COLUMN = "process_version"


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    if not _column_exists(PROCESS_INSTANCE_TABLE, PROCESS_VERSION_COLUMN):
        return

    with op.batch_alter_table(PROCESS_INSTANCE_TABLE, schema=None) as batch_op:
        batch_op.drop_column(PROCESS_VERSION_COLUMN)


def downgrade() -> None:
    if _column_exists(PROCESS_INSTANCE_TABLE, PROCESS_VERSION_COLUMN):
        return

    with op.batch_alter_table(PROCESS_INSTANCE_TABLE, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                PROCESS_VERSION_COLUMN,
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )

    with op.batch_alter_table(PROCESS_INSTANCE_TABLE, schema=None) as batch_op:
        batch_op.alter_column(
            PROCESS_VERSION_COLUMN,
            existing_type=sa.Integer(),
            existing_nullable=False,
            existing_server_default=sa.text("1"),
            server_default=None,
        )
