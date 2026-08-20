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


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _schema() -> str | None:
    try:
        return getattr(op.get_context(), "version_table_schema", None)
    except Exception:
        return None


def _table_exists(inspector: sa.Inspector | None = None, schema: str | None | object = ...) -> bool:
    insp = inspector if inspector is not None else _inspector()
    sch = _schema() if schema is ... else schema  # type: ignore[assignment]
    if insp.has_table(TABLE_NAME, schema=sch):
        return True
    return TABLE_NAME in insp.get_table_names(schema=sch)


def _column_exists(inspector: sa.Inspector | None = None, schema: str | None | object = ...) -> bool:
    insp = inspector if inspector is not None else _inspector()
    sch = _schema() if schema is ... else schema  # type: ignore[assignment]
    if not _table_exists(inspector=insp, schema=sch):
        return False
    try:
        columns = insp.get_columns(TABLE_NAME, schema=sch)
        return any(column["name"] == COLUMN_NAME for column in columns)
    except Exception:
        return False


def upgrade():
    # Additive and nullable: existing rows keep their data and read back as NULL.
    insp = _inspector()
    schema = _schema()
    if _table_exists(inspector=insp, schema=schema) and not _column_exists(inspector=insp, schema=schema):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.String(length=COLUMN_LENGTH), nullable=True),
            schema=schema,
        )


def downgrade():
    # Drops diagnostic text only; no request state lives in this column.
    insp = _inspector()
    schema = _schema()
    if _column_exists(inspector=insp, schema=schema):
        with op.batch_alter_table(TABLE_NAME, schema=schema) as batch_op:
            batch_op.drop_column(COLUMN_NAME)
