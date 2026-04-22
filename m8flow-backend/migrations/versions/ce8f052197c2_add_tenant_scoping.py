from alembic import op
import sqlalchemy as sa

from m8flow_backend.tenancy import DEFAULT_TENANT_ID

revision = "ce8f052197c2"
down_revision = "1518b05122bc"
branch_labels = None
depends_on = None

# List of tables to add tenant scoping to
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


def _drop_unique_by_columns(table: str, columns: list[str]) -> None:
    insp = _inspector()
    for uc in insp.get_unique_constraints(table):
        if uc.get("column_names") == columns:
            op.drop_constraint(uc["name"], table, type_="unique")
    for idx in insp.get_indexes(table):
        if idx.get("unique") and idx.get("column_names") == columns:
            op.drop_index(idx["name"], table_name=table)


def _drop_unique_by_name(table: str, name: str) -> None:
    insp = _inspector()
    for uc in insp.get_unique_constraints(table):
        if uc.get("name") == name:
            op.drop_constraint(name, table, type_="unique")


def _get_backfill_tenant_id() -> str:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO m8flow_tenant (id, name) VALUES (:tenant_id, :tenant_name) "
            "ON CONFLICT (id) DO NOTHING"
        ).bindparams(tenant_id=DEFAULT_TENANT_ID, tenant_name=DEFAULT_TENANT_ID)
    )
    tenant_id = conn.execute(
        sa.text("SELECT id FROM m8flow_tenant WHERE id = :tenant_id").bindparams(
            tenant_id=DEFAULT_TENANT_ID
        )
    ).scalar()
    if tenant_id != DEFAULT_TENANT_ID:
        raise RuntimeError(
            "Missing default tenant. Insert id='default' into m8flow_tenant before applying 0002_add_tenant_scoping."
        )
    return tenant_id


def upgrade() -> None:
    tenant_id = _get_backfill_tenant_id()
    for table in TENANT_TABLES:
        if not _column_exists(table, "m8f_tenant_id"):
            with op.batch_alter_table(table) as batch_op:
                batch_op.add_column(sa.Column("m8f_tenant_id", sa.String(255), nullable=True))

        op.execute(
            sa.text(f"UPDATE {table} SET m8f_tenant_id = :tenant_id WHERE m8f_tenant_id IS NULL")
            .bindparams(tenant_id=tenant_id)
        )

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

    _drop_unique_by_columns("bpmn_process_definition", ["full_process_model_hash"])
    _drop_unique_by_name("bpmn_process_definition", "process_hash_unique")
    op.create_unique_constraint(
        "bpmn_process_definition_full_process_model_hash_tenant_unique",
        "bpmn_process_definition",
        ["m8f_tenant_id", "full_process_model_hash"],
    )
    op.create_unique_constraint(
        "process_hash_unique",
        "bpmn_process_definition",
        ["m8f_tenant_id", "full_process_model_hash", "single_process_hash"],
    )

    _drop_unique_by_name("task_definition", "task_definition_unique")
    op.create_unique_constraint(
        "task_definition_unique",
        "task_definition",
        ["m8f_tenant_id", "bpmn_process_definition_id", "bpmn_identifier"],
    )

    _drop_unique_by_name("message", "message_identifier_location_unique")
    op.create_unique_constraint(
        "message_identifier_location_unique",
        "message",
        ["m8f_tenant_id", "identifier", "location"],
    )

    _drop_unique_by_columns("message_triggerable_process_model", ["message_name"])
    op.create_unique_constraint(
        "message_triggerable_process_model_message_name_tenant_unique",
        "message_triggerable_process_model",
        ["m8f_tenant_id", "message_name"],
    )

    _drop_unique_by_name("json_data_store", "_identifier_location_unique")
    op.create_unique_constraint(
        "_identifier_location_unique",
        "json_data_store",
        ["m8f_tenant_id", "identifier", "location"],
    )

    _drop_unique_by_name("kkv_data_store", "_kkv_identifier_location_unique")
    op.create_unique_constraint(
        "_kkv_identifier_location_unique",
        "kkv_data_store",
        ["m8f_tenant_id", "identifier", "location"],
    )

    _drop_unique_by_name("process_instance_report", "process_instance_report_unique")
    op.create_unique_constraint(
        "process_instance_report_unique",
        "process_instance_report",
        ["m8f_tenant_id", "created_by_id", "identifier"],
    )

    _drop_unique_by_name("reference_cache", "reference_cache_uniq")
    op.create_unique_constraint(
        "reference_cache_uniq",
        "reference_cache",
        ["m8f_tenant_id", "generation_id", "identifier", "relative_location", "type"],
    )

    _drop_unique_by_columns("secret", ["key"])
    op.create_unique_constraint(
        "secret_key_tenant_unique",
        "secret",
        ["m8f_tenant_id", "key"],
    )

    _drop_unique_by_name("service_account", "service_account_uniq")
    op.create_unique_constraint(
        "service_account_uniq",
        "service_account",
        ["m8f_tenant_id", "name", "created_by_user_id"],
    )


def downgrade() -> None:
    _drop_unique_by_name("service_account", "service_account_uniq")
    op.create_unique_constraint(
        "service_account_uniq",
        "service_account",
        ["name", "created_by_user_id"],
    )

    _drop_unique_by_name("secret", "secret_key_tenant_unique")
    op.create_unique_constraint(
        "secret_key_unique",
        "secret",
        ["key"],
    )

    _drop_unique_by_name("reference_cache", "reference_cache_uniq")
    op.create_unique_constraint(
        "reference_cache_uniq",
        "reference_cache",
        ["generation_id", "identifier", "relative_location", "type"],
    )

    _drop_unique_by_name("process_instance_report", "process_instance_report_unique")
    op.create_unique_constraint(
        "process_instance_report_unique",
        "process_instance_report",
        ["created_by_id", "identifier"],
    )

    _drop_unique_by_name("kkv_data_store", "_kkv_identifier_location_unique")
    op.create_unique_constraint(
        "_kkv_identifier_location_unique",
        "kkv_data_store",
        ["identifier", "location"],
    )

    _drop_unique_by_name("json_data_store", "_identifier_location_unique")
    op.create_unique_constraint(
        "_identifier_location_unique",
        "json_data_store",
        ["identifier", "location"],
    )

    _drop_unique_by_name("message", "message_identifier_location_unique")
    op.create_unique_constraint(
        "message_identifier_location_unique",
        "message",
        ["identifier", "location"],
    )

    _drop_unique_by_name("task_definition", "task_definition_unique")
    op.create_unique_constraint(
        "task_definition_unique",
        "task_definition",
        ["bpmn_process_definition_id", "bpmn_identifier"],
    )

    _drop_unique_by_name("bpmn_process_definition", "process_hash_unique")
    _drop_unique_by_name("bpmn_process_definition", "bpmn_process_definition_full_process_model_hash_tenant_unique")
    op.create_unique_constraint(
        "bpmn_process_definition_full_process_model_hash_unique",
        "bpmn_process_definition",
        ["full_process_model_hash"],
    )
    op.create_unique_constraint(
        "process_hash_unique",
        "bpmn_process_definition",
        ["full_process_model_hash", "single_process_hash"],
    )

    _drop_unique_by_name("message_triggerable_process_model", "message_triggerable_process_model_message_name_tenant_unique")
    op.create_unique_constraint(
        "message_triggerable_process_model_message_name_unique",
        "message_triggerable_process_model",
        ["message_name"],
    )

    for table in TENANT_TABLES:
        index_name = f"ix_{table}_m8f_tenant_id"
        if _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)

        for fk_name in _fk_names_for_column(table, "m8f_tenant_id"):
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_constraint(fk_name, type_="foreignkey")

        if _column_exists(table, "m8f_tenant_id"):
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_column("m8f_tenant_id")