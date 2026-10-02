"""Remove legacy epoch columns from m8flow-bpmn-core tables.

The 0.1.2 core wheel owns the models and the core repository owns the
canonical migration history, but the M8Flow container runs this repository's
Alembic environment. Keep the deployment migration here so upgrading M8Flow
actually applies the schema change that the vendored wheel expects.

The datetime columns were added and backfilled by the 0.1.2 compatibility
migration before this revision. Downgrade restores empty columns only; deleted
epoch values cannot be reconstructed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


CORE_LEGACY_COLUMNS: dict[str, tuple[str, ...]] = {
    "user": ("created_at_in_seconds", "updated_at_in_seconds"),
    "m8flow_tenant": ("created_at_in_seconds", "updated_at_in_seconds"),
    "bpmn_process_definition": ("created_at_in_seconds", "updated_at_in_seconds"),
    "bpmn_process": ("start_in_seconds", "end_in_seconds"),
    "task_definition": ("created_at_in_seconds", "updated_at_in_seconds"),
    "task": ("start_in_seconds", "end_in_seconds"),
    "process_instance": (
        "start_in_seconds",
        "end_in_seconds",
        "task_updated_at_in_seconds",
        "created_at_in_seconds",
        "updated_at_in_seconds",
    ),
    "human_task": ("created_at_in_seconds", "updated_at_in_seconds"),
    "work_item": ("created_at_in_seconds", "updated_at_in_seconds"),
    "future_task": (
        "run_at_in_seconds",
        "queued_to_run_at_in_seconds",
        "updated_at_in_seconds",
    ),
    "process_instance_metadata": ("created_at_in_seconds", "updated_at_in_seconds"),
    "process_instance_event": ("timestamp",),
    "process_model_bpmn_version": ("created_at_in_seconds",),
    "scheduler_job": (
        "locked_at_in_seconds",
        "run_at_in_seconds",
        "created_at_in_seconds",
        "updated_at_in_seconds",
    ),
}


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _drop(table_name: str, requested: tuple[str, ...]) -> None:
    existing = [column for column in requested if column in _columns(table_name)]
    if not existing:
        return

    existing_names = set(existing)
    inspector = sa.inspect(op.get_bind())
    for index in inspector.get_indexes(table_name):
        if existing_names.intersection(index.get("column_names", ())):
            op.drop_index(index["name"], table_name=table_name)

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            for column in existing:
                batch_op.drop_column(column)
        return

    for column in existing:
        op.drop_column(table_name, column)


def upgrade() -> None:
    for table_name, columns in CORE_LEGACY_COLUMNS.items():
        _drop(table_name, columns)


def downgrade() -> None:
    for table_name, columns in reversed(tuple(CORE_LEGACY_COLUMNS.items())):
        if not _columns(table_name):
            continue
        existing = _columns(table_name)
        missing = [column for column in columns if column not in existing]
        if not missing:
            continue
        definitions = [
            sa.Column(
                column,
                sa.Numeric(17, 6)
                if column == "timestamp" or (
                    table_name in {"bpmn_process", "task"}
                    and column in {"start_in_seconds", "end_in_seconds"}
                )
                else sa.BigInteger(),
                nullable=True,
            )
            for column in missing
        ]
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table_name, recreate="always") as batch_op:
                for definition in definitions:
                    batch_op.add_column(definition)
        else:
            for definition in definitions:
                op.add_column(table_name, definition)

    for table_name, index_name, column_name in (
        ("process_instance", "ix_process_instance_start_in_seconds", "start_in_seconds"),
        ("process_instance", "ix_process_instance_end_in_seconds", "end_in_seconds"),
        ("future_task", "ix_future_task_run_at_in_seconds", "run_at_in_seconds"),
        ("future_task", "ix_future_task_queued_to_run_at_in_seconds", "queued_to_run_at_in_seconds"),
        (
            "process_model_bpmn_version",
            "ix_process_model_bpmn_version_created_at_in_seconds",
            "created_at_in_seconds",
        ),
        ("scheduler_job", "ix_scheduler_job_locked_at_in_seconds", "locked_at_in_seconds"),
        ("scheduler_job", "ix_scheduler_job_run_at_in_seconds", "run_at_in_seconds"),
        ("process_instance_event", "ix_process_instance_event_timestamp", "timestamp"),
    ):
        if column_name in _columns(table_name):
            existing_indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table_name)}
            if index_name not in existing_indexes:
                op.create_index(index_name, table_name, [column_name])
