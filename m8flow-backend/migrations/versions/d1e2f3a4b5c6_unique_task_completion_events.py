"""Make task completion event writes idempotent across concurrent requests.

The index applies only to task completion events with a task GUID. Existing
duplicate audit rows are never deleted: an upgrade reports the duplicate keys
and stops so an operator can reconcile them before retrying the migration.
PostgreSQL and SQLite use partial unique indexes; MySQL and MariaDB use a
nullable generated column with a unique index because they do not support
partial indexes.
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
MYSQL_UNIQUE_COLUMN = "task_completed_unique_task_guid"


def _mysql_unique_column() -> sa.Column:
    return sa.Column(
        MYSQL_UNIQUE_COLUMN,
        sa.String(length=36),
        sa.Computed(
            "CASE WHEN event_type = 'task_completed' THEN task_guid ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )


def _create_unique_index(dialect: str, inspector) -> None:
    if dialect in {"postgresql", "sqlite"}:
        predicate = sa.and_(
            sa.column("event_type") == "task_completed",
            sa.column("task_guid").is_not(None),
        )
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            ["m8f_tenant_id", "process_instance_id", "task_guid"],
            unique=True,
            postgresql_where=predicate,
            sqlite_where=predicate,
        )
        return

    if dialect in {"mysql", "mariadb"}:
        columns = {item["name"] for item in inspector.get_columns(TABLE_NAME)}
        if MYSQL_UNIQUE_COLUMN not in columns:
            op.add_column(TABLE_NAME, _mysql_unique_column())
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            ["m8f_tenant_id", "process_instance_id", MYSQL_UNIQUE_COLUMN],
            unique=True,
        )
        return

    raise RuntimeError(
        "Unique task completion events require partial-index or generated-column support; "
        f"database dialect {dialect!r} is not supported."
    )


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

    dialect = bind.dialect.name
    if dialect not in {"postgresql", "sqlite", "mysql", "mariadb"}:
        raise RuntimeError(
            "Unique task completion events require partial-index or generated-column support; "
            f"database dialect {dialect!r} is not supported."
        )

    events = sa.Table(TABLE_NAME, sa.MetaData(), autoload_with=bind)
    tenant_column = events.c.m8f_tenant_id
    instance_column = events.c.process_instance_id
    task_guid_column = events.c.task_guid
    completion_predicate = sa.and_(
        events.c.event_type == "task_completed",
        task_guid_column.is_not(None),
    )
    duplicate_query = (
        sa.select(
            tenant_column,
            instance_column,
            task_guid_column,
            sa.func.count().label("event_count"),
        )
        .where(completion_predicate)
        .group_by(tenant_column, instance_column, task_guid_column)
        .having(sa.func.count() > 1)
        .order_by(tenant_column, instance_column, task_guid_column)
    )
    duplicates = bind.execute(duplicate_query).all()
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

    _create_unique_index(dialect, inspector)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _table_exists(inspector) and INDEX_NAME in {
        item["name"] for item in inspector.get_indexes(TABLE_NAME)
    }:
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    if bind.dialect.name in {"mysql", "mariadb"} and _table_exists(inspector):
        columns = {item["name"] for item in inspector.get_columns(TABLE_NAME)}
        if MYSQL_UNIQUE_COLUMN in columns:
            op.drop_column(TABLE_NAME, MYSQL_UNIQUE_COLUMN)
