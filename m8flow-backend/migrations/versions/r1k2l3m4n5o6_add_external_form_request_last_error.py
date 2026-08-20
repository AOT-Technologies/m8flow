"""Add last_error to m8flow_external_form_requests

Reverses the "no last_error column" decision recorded in k3c4d5e6f7a9. That note assumed
failure reasons only ever needed to reach an operator reading worker logs. They also need
to reach a tenant admin in the UI: a request parked in the new ``smtp_unconfigured`` status
is useless to diagnose without knowing which NATS_SMTP_* secrets were missing, and a
generic SMTP rejection is equally opaque.

The column is bounded (500 chars, truncated on write) and only ever receives text that is
already being logged — never a secret value.

Revision ID: r1k2l3m4n5o6
Revises: q0j1k2l3m4n5
Create Date: 2026-08-19

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "r1k2l3m4n5o6"
down_revision = "q0j1k2l3m4n5"
branch_labels = None
depends_on = None

TABLE_NAME = "m8flow_external_form_requests"
COLUMN_NAME = "last_error"
COLUMN_LENGTH = 500


def _table_exists() -> bool:
    return TABLE_NAME in sa.inspect(op.get_bind()).get_table_names()


def _column_exists() -> bool:
    # Callers must check _table_exists() first: "no such column" and "no such table" are
    # both false here, and only the former is safe to ALTER.
    if not _table_exists():
        return False
    return any(column["name"] == COLUMN_NAME for column in sa.inspect(op.get_bind()).get_columns(TABLE_NAME))


def upgrade():
    # Additive and nullable: existing rows keep their data and read back as NULL.
    if _table_exists() and not _column_exists():
        op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.String(length=COLUMN_LENGTH), nullable=True))


def downgrade():
    # Drops diagnostic text only; no request state lives in this column.
    if _column_exists():
        with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
            batch_op.drop_column(COLUMN_NAME)
