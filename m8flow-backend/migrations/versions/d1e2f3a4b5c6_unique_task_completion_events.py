"""Make task completion event writes idempotent across concurrent requests.

The index applies only to task completion events with a task GUID. Existing
duplicate audit rows are never deleted: an upgrade reports the duplicate keys
and stops so an operator can reconcile them before retrying the migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "d1e2f3a4b5c6"
down_revision = "c1e4f5a6b7d8"
branch_labels = None
depends_on = None

TABLE_NAME = "process_instance_event"
INDEX_NAME = "uq_process_instance_event_task_completed_once"
PREDICATE = "event_type = 'task_completed' AND task_guid IS NOT NULL"


def _table_exists(inspector) -> bool:
    return TABLE_NAME in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector):
        return

    existing_indexes = {item["name"] for item in inspector.get_indexes(TABLE_NAME)}
    if INDEX_NAME in existing_indexes:
        return

    duplicates = bind.execute(
        sa.text(
            f"SELECT m8f_tenant_id, process_instance_id, task_guid, COUNT(*) "
            f"FROM {TABLE_NAME} WHERE {PREDICATE} "
            "GROUP BY m8f_tenant_id, process_instance_id, task_guid HAVING COUNT(*) > 1 "
            "ORDER BY m8f_tenant_id, process_instance_id, task_guid"
        )
    ).all()
    if duplicates:
        formatted = "; ".join(
            f"tenant={tenant!r}, process_instance={instance_id}, task_guid={task_guid!r}, rows={count}"
            for tenant, instance_id, task_guid, count in duplicates[:20]
        )
        more = " (additional duplicate keys omitted)" if len(duplicates) > 20 else ""
        raise RuntimeError(
            "Cannot enforce unique task completion events because existing duplicates "
            f"were found: {formatted}{more}. Reconcile these audit rows without deleting "
            "history, then rerun the migration."
        )

    dialect = bind.dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError(
            "Unique task completion events require partial-index support; "
            f"database dialect {dialect!r} is not supported."
        )
    predicate = sa.text(PREDICATE)
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["m8f_tenant_id", "process_instance_id", "task_guid"],
        unique=True,
        postgresql_where=predicate,
        sqlite_where=predicate,
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _table_exists(inspector) and INDEX_NAME in {
        item["name"] for item in inspector.get_indexes(TABLE_NAME)
    }:
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
