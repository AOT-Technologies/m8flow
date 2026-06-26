"""Align scheduler_job schema with m8flow_bpmn_core revision f1a2b3c4d5e6.

Revision ID: m6f7a8b9c0d1
Revises: l5e6f7a8b9c0
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "m6f7a8b9c0d1"
down_revision = "l5e6f7a8b9c0"
branch_labels = None
depends_on = None

SCHEDULER_JOB_TABLE = "scheduler_job"
EXPECTED_COLUMNS = {
    "id",
    "job_key",
    "job_type",
    "process_instance_id",
    "bpmn_process_definition_id",
    "locked_by",
    "locked_at_in_seconds",
    "run_at_in_seconds",
    "payload_json",
    "updated_at_in_seconds",
    "created_at_in_seconds",
    "m8f_tenant_id",
}
EXPECTED_INDEXES: tuple[tuple[str, list[str]], ...] = (
    ("ix_scheduler_job_bpmn_process_definition_id", ["bpmn_process_definition_id"]),
    ("ix_scheduler_job_job_type", ["job_type"]),
    ("ix_scheduler_job_locked_at_in_seconds", ["locked_at_in_seconds"]),
    ("ix_scheduler_job_locked_by", ["locked_by"]),
    ("ix_scheduler_job_m8f_tenant_id", ["m8f_tenant_id"]),
    ("ix_scheduler_job_process_instance_id", ["process_instance_id"]),
    ("ix_scheduler_job_run_at_in_seconds", ["run_at_in_seconds"]),
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _index_exists(table_name: str, columns: list[str]) -> bool:
    for index in _inspector().get_indexes(table_name):
        if list(index.get("column_names") or []) == columns:
            return True
    return False


def _unique_exists(table_name: str, columns: list[str]) -> bool:
    for constraint in _inspector().get_unique_constraints(table_name):
        if list(constraint.get("column_names") or []) == columns:
            return True
    return False


def _foreign_key_exists(
    table_name: str,
    constrained_columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> bool:
    for foreign_key in _inspector().get_foreign_keys(table_name):
        if foreign_key.get("referred_table") != referred_table:
            continue
        if list(foreign_key.get("constrained_columns") or []) != constrained_columns:
            continue
        if list(foreign_key.get("referred_columns") or []) != referred_columns:
            continue
        return True
    return False


def _scheduler_job_has_compatible_shape() -> bool:
    if not _table_exists(SCHEDULER_JOB_TABLE):
        return False
    if _column_names(SCHEDULER_JOB_TABLE) != EXPECTED_COLUMNS:
        return False
    if not _unique_exists(SCHEDULER_JOB_TABLE, ["m8f_tenant_id", "job_key"]):
        return False
    if not _foreign_key_exists(
        SCHEDULER_JOB_TABLE,
        ["bpmn_process_definition_id"],
        "bpmn_process_definition",
        ["id"],
    ):
        return False
    if not _foreign_key_exists(
        SCHEDULER_JOB_TABLE,
        ["m8f_tenant_id"],
        "m8flow_tenant",
        ["id"],
    ):
        return False
    if not _foreign_key_exists(
        SCHEDULER_JOB_TABLE,
        ["process_instance_id"],
        "process_instance",
        ["id"],
    ):
        return False
    return True


def _ensure_indexes() -> None:
    for index_name, columns in EXPECTED_INDEXES:
        if _index_exists(SCHEDULER_JOB_TABLE, columns):
            continue
        op.create_index(index_name, SCHEDULER_JOB_TABLE, columns, unique=False)


def _create_scheduler_job_table() -> None:
    op.create_table(
        SCHEDULER_JOB_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_key", sa.String(length=255), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("process_instance_id", sa.Integer(), nullable=True),
        sa.Column("bpmn_process_definition_id", sa.Integer(), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("locked_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("run_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["bpmn_process_definition_id"],
            ["bpmn_process_definition.id"],
            name=op.f(
                "fk_scheduler_job_bpmn_process_definition_id_bpmn_process_definition"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["m8f_tenant_id"],
            ["m8flow_tenant.id"],
            name=op.f("fk_scheduler_job_m8f_tenant_id_m8flow_tenant"),
        ),
        sa.ForeignKeyConstraint(
            ["process_instance_id"],
            ["process_instance.id"],
            name=op.f("fk_scheduler_job_process_instance_id_process_instance"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduler_job")),
        sa.UniqueConstraint(
            "m8f_tenant_id",
            "job_key",
            name="uq_scheduler_job_tenant_job_key",
        ),
    )
    _ensure_indexes()


def upgrade() -> None:
    if not _table_exists(SCHEDULER_JOB_TABLE):
        _create_scheduler_job_table()
        return

    if not _scheduler_job_has_compatible_shape():
        raise RuntimeError(
            "Cannot align scheduler_job schema with m8flow_bpmn_core compatibility "
            "rules because the existing scheduler_job table is incompatible."
        )

    _ensure_indexes()


def downgrade() -> None:
    if _table_exists(SCHEDULER_JOB_TABLE):
        op.drop_table(SCHEDULER_JOB_TABLE)
