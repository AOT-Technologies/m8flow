"""Add last_error to m8flow_external_form_requests.

Why a column and not just the worker log: when delivery fails, the only record of
*why* lived in the notification worker's stdout. An admin looking at a stuck
request in the API could see status='failed' and an attempt count, with no way to
tell a bad SMTP password from a rejected recipient. `last_error` carries that
reason back to the tracking row, bounded to
``ExternalFormRequestModel.LAST_ERROR_MAX_LENGTH`` (writers truncate; an SMTP
rejection is routinely longer).

Databases created by the root revision already have this column -- it builds from
the live ORM metadata -- so this revision is a no-op there. It exists for
databases stamped at 1518b05122bc before the column was added to the model.

Revision ID: a1b2c3d4e5f6
Revises: 1518b05122bc
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from m8flow_backend.models.external_form_request import LAST_ERROR_MAX_LENGTH

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "1518b05122bc"
branch_labels = None
depends_on = None

TABLE_NAME = "m8flow_external_form_requests"
COLUMN_NAME = "last_error"


def _column_state() -> tuple[bool, bool]:
    """(table exists, column exists) -- both guards matter: the root revision may have
    already created the column from ORM metadata, and a partially built database may not
    have the table at all."""
    inspector = sa.inspect(op.get_bind())
    if TABLE_NAME not in inspector.get_table_names():
        return False, False
    return True, COLUMN_NAME in {column["name"] for column in inspector.get_columns(TABLE_NAME)}


def upgrade() -> None:
    table_exists, column_exists = _column_state()
    if not table_exists or column_exists:
        return
    op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.String(LAST_ERROR_MAX_LENGTH), nullable=True))


def downgrade() -> None:
    table_exists, column_exists = _column_state()
    if not table_exists or not column_exists:
        return
    op.drop_column(TABLE_NAME, COLUMN_NAME)
