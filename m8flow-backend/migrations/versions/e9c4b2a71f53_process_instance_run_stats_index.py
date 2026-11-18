"""Index the Processes page run stats (M8F-703).

``workflow.process_model_run_stats`` groups a tenant's instances by process
model for last_run_at and runs_30d. With only the single-column tenant index,
Postgres reads every instance row of the tenant; this composite index serves
the filter, the grouping and both aggregates. Measured with the real schema:
16.4 -> 6.8 ms at 50k instances per tenant, 47.7 -> 15.3 ms at 200k.

Adds an index only; no data changes. On PostgreSQL it is built and dropped
CONCURRENTLY, so the backend's startup upgrade never blocks writes to
process_instance. CONCURRENTLY cannot run inside a transaction, so that step
commits the migrations before it first (``autocommit_block``). An interrupted
concurrent build leaves an INVALID index behind; the next upgrade drops and
rebuilds it. Guarded so reruns and downgrades are idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e9c4b2a71f53"
down_revision = "c7e9a1b3d5f7"
branch_labels = None
depends_on = None

TABLE_NAME = "process_instance"
INDEX_NAME = "ix_process_instance_tenant_model_started"
COLUMNS = ["m8f_tenant_id", "process_model_identifier", "started_at"]


def _index_names() -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(TABLE_NAME)}


def _postgres_index_is_valid() -> bool | None:
    """True/False for an existing index's validity; None when it does not exist."""
    return op.get_bind().execute(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname = :name"
        ),
        {"name": INDEX_NAME},
    ).scalar()


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        if INDEX_NAME not in _index_names():
            op.create_index(INDEX_NAME, TABLE_NAME, COLUMNS, unique=False)
        return
    with op.get_context().autocommit_block():
        valid = _postgres_index_is_valid()
        if valid is False:
            op.drop_index(INDEX_NAME, table_name=TABLE_NAME, postgresql_concurrently=True)
        if valid is not True:
            op.create_index(INDEX_NAME, TABLE_NAME, COLUMNS, unique=False, postgresql_concurrently=True)


def downgrade() -> None:
    if INDEX_NAME not in _index_names():
        return
    if op.get_bind().dialect.name != "postgresql":
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
        return
    with op.get_context().autocommit_block():
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME, postgresql_concurrently=True)
