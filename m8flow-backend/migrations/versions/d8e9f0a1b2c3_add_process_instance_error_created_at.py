"""Add created_at to m8flow_process_instance_error.

``created_at_in_seconds`` holds whole seconds, so an error row written in the
same second as a retry could not be placed in the right execution attempt
(M8F-675 review). ``created_at`` keeps the full timestamp, comparable with
``process_instance_event.occurred_at``. Existing rows stay NULL and keep the
whole-second fallback.

Databases created by the root revision already have this column -- it builds
from the live ORM metadata -- so this revision is a no-op there.

Revision ID: d8e9f0a1b2c3
Revises: e9c4b2a71f53
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d8e9f0a1b2c3"
down_revision = "e9c4b2a71f53"
branch_labels = None
depends_on = None

TABLE_NAME = "m8flow_process_instance_error"
COLUMN_NAME = "created_at"


def _column_state() -> tuple[bool, bool]:
    """(table exists, column exists)."""
    inspector = sa.inspect(op.get_bind())
    if TABLE_NAME not in inspector.get_table_names():
        return False, False
    return True, COLUMN_NAME in {column["name"] for column in inspector.get_columns(TABLE_NAME)}


def upgrade() -> None:
    table_exists, column_exists = _column_state()
    if not table_exists or column_exists:
        return
    op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    table_exists, column_exists = _column_state()
    if not table_exists or not column_exists:
        return
    op.drop_column(TABLE_NAME, COLUMN_NAME)
