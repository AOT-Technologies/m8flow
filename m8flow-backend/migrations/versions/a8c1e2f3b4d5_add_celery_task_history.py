"""Add m8flow_celery_task (Celery task history for the System -> Celery page).

Celery keeps no task history, so workers record each task's lifecycle here from their
own signals (M8F-602). Purely additive.

Databases created by the root revision already have this table -- it builds from the
live ORM metadata -- so the create is skipped there (same guard as b7e1c2d3f4a5). No
row-level-security policy: this is global operations data read by super-admins only,
and the table deliberately has no ``m8f_tenant_id`` column.

Revision ID: a8c1e2f3b4d5
Revises: b8c9d0e1f2a3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a8c1e2f3b4d5"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None

TABLE_NAME = "m8flow_celery_task"
INDEXED_COLUMNS = ("name", "state", "worker", "tenant_id", "updated_at")


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE_NAME)


def upgrade() -> None:
    if _table_exists():
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("worker", sa.String(length=255), nullable=True),
        sa.Column("queue", sa.String(length=255), nullable=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("args", sa.Text(), nullable=True),
        sa.Column("kwargs", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("exception", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("eta", sa.String(length=64), nullable=True),
        sa.Column("expires", sa.String(length=64), nullable=True),
        sa.Column("parent_id", sa.String(length=255), nullable=True),
        sa.Column("root_id", sa.String(length=255), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runtime_seconds", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # Same name the host naming convention gives the model's primary key.
        sa.PrimaryKeyConstraint("task_id", name=f"pk_host_{TABLE_NAME}"),
    )
    for column in INDEXED_COLUMNS:
        op.create_index(f"ix_host_{TABLE_NAME}_{column}", TABLE_NAME, [column], unique=False)


def downgrade() -> None:
    # Dropping the table drops its indexes with it. Task history is diagnostic data only.
    if _table_exists():
        op.drop_table(TABLE_NAME)
