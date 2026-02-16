from alembic import op
import sqlalchemy as sa

revision = "a750bbb5c234"
down_revision = "ce8f052197c2"
branch_labels = None
depends_on = None

# Tenant-scoped tables (must have m8f_tenant_id).
TENANT_TABLES = [
    "api_log",
    "bpmn_process",
    "bpmn_process_definition",
    "bpmn_process_definition_relationship",
    "future_task",
    "human_task",
    "human_task_user",
    "json_data_store",
    "kkv_data_store",
    "kkv_data_store_entry",
    "message",
    "message_correlation_property",
    "message_instance",
    "message_instance_correlation_rule",
    "message_triggerable_process_model",
    "process_caller_cache",
    "process_caller_relationship",
    "process_instance",
    "process_instance_error_detail",
    "process_instance_event",
    "process_instance_file_data",
    "process_instance_metadata",
    "process_instance_migration_detail",
    "process_instance_queue",
    "process_instance_report",
    "process_model_cycle",
    "reference_cache",
    "secret",
    "service_account",
    "task",
    "task_definition",
    "task_draft_data",
    "task_instructions_for_end_user",
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _inspector():
    return sa.inspect(op.get_bind())


def _column_exists(table: str, column: str) -> bool:
    insp = _inspector()
    return column in [c["name"] for c in insp.get_columns(table)]


def _index_exists(table: str, index_name: str) -> bool:
    insp = _inspector()
    return any(idx["name"] == index_name for idx in insp.get_indexes(table))


def _fk_names_for_column(table: str, column: str) -> list[str]:
    insp = _inspector()
    names = []
    for fk in insp.get_foreign_keys(table):
        if column in fk.get("constrained_columns", []):
            if fk.get("name"):
                names.append(fk["name"])
    return names


def _null_tenant_count(table: str) -> int:
    conn = op.get_bind()
    return conn.execute(sa.text(f"SELECT count(*) FROM {table} WHERE m8f_tenant_id IS NULL")).scalar()


def _ensure_rls(table: str) -> None:
    policy_name = f"{table}_tenant_isolation"
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {policy_name} ON {table} "
            "USING (m8f_tenant_id = current_setting('app.current_tenant', true)) "
            "WITH CHECK (m8f_tenant_id = current_setting('app.current_tenant', true))"
        )
    )


def upgrade() -> None:
    if not _is_postgres():
        return

    for table in TENANT_TABLES:
        if not _column_exists(table, "m8f_tenant_id"):
            continue

        if _null_tenant_count(table) != 0:
            raise RuntimeError(f"Table {table} has rows with NULL m8f_tenant_id; backfill before enabling RLS.")

        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("m8f_tenant_id", nullable=False)

        fk_name = f"{table}_m8f_tenant_id_fkey"
        if not _fk_names_for_column(table, "m8f_tenant_id"):
            op.create_foreign_key(
                fk_name,
                table,
                "m8flow_tenant",
                ["m8f_tenant_id"],
                ["id"],
                ondelete="RESTRICT",
            )

        index_name = f"ix_{table}_m8f_tenant_id"
        if not _index_exists(table, index_name):
            op.create_index(index_name, table, ["m8f_tenant_id"])

        _ensure_rls(table)


def downgrade() -> None:
    if not _is_postgres():
        return

    for table in TENANT_TABLES:
        if not _column_exists(table, "m8f_tenant_id"):
            continue
        policy_name = f"{table}_tenant_isolation"
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))