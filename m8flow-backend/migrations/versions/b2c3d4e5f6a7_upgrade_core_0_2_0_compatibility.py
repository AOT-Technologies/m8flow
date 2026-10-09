"""Upgrade existing M8Flow databases for m8flow-bpmn-core 0.2.0.

The backend uses a squashed schema root, while the core package carries its
own longer migration history.  A database created by the current root already
has the 0.2.0 shape, so every operation below is guarded and becomes a no-op
for that case.  Databases created with core 0.1.1 receive the additive schema
and data-preserving compatibility changes here.

The JSON migration deliberately aborts before changing the old table when it
finds an orphaned payload, a missing reference, an unknown tenant, or a null
tenant/reference.  Those cases require operator data repair rather than a
best-effort migration that could leak or discard tenant data.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from typing import Any, Callable

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

_TENANT_RLS_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_RLS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"

_SQLITE_PENDING_TABLE_OPERATIONS: dict[str, list[Callable[[Any], None]]] = {}
_SQLITE_PENDING_CONSTRAINTS: set[tuple[str, str]] = set()


TIMESTAMP_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "user": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "m8flow_tenant": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "bpmn_process_definition": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "bpmn_process": (("start_in_seconds", "started_at"), ("end_in_seconds", "ended_at")),
    "task_definition": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "task": (("start_in_seconds", "started_at"), ("end_in_seconds", "ended_at")),
    "process_instance": (
        ("start_in_seconds", "started_at"),
        ("end_in_seconds", "ended_at"),
        ("task_updated_at_in_seconds", "task_updated_at"),
        ("created_at_in_seconds", "created_at"),
        ("updated_at_in_seconds", "updated_at"),
    ),
    "human_task": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "future_task": (
        ("run_at_in_seconds", "run_at"),
        ("queued_to_run_at_in_seconds", "queued_to_run_at"),
        ("updated_at_in_seconds", "updated_at"),
    ),
    "process_instance_event": (("timestamp", "occurred_at"),),
    "process_instance_metadata": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "process_model_bpmn_version": (("created_at_in_seconds", "created_at"),),
    "scheduler_job": (
        ("locked_at_in_seconds", "locked_at"),
        ("run_at_in_seconds", "run_at"),
        ("created_at_in_seconds", "created_at"),
        ("updated_at_in_seconds", "updated_at"),
    ),
    # M8Flow-owned tables use the same additive compatibility contract as
    # core-owned tables.  Keep the epoch columns until downstream consumers
    # have migrated to the native datetime fields.
    "secret": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "pkce_code_verifier": (("created_at_in_seconds", "created_at"),),
    "refresh_token": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "service_account": (("created_at_in_seconds", "created_at"),),
    "task_draft_data": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "task_instructions_for_end_user": (("created_at_in_seconds", "created_at"),),
    "api_log": (("created_at_in_seconds", "created_at"),),
    "process_instance_file_data": (("created_at_in_seconds", "created_at"),),
    "m8flow_templates": (("created_at_in_seconds", "created_at"), ("updated_at_in_seconds", "updated_at")),
    "m8flow_process_model_template": (
        ("created_at_in_seconds", "created_at"),
        ("updated_at_in_seconds", "updated_at"),
    ),
    "m8flow_nats_api_key": (
        ("created_at_in_seconds", "created_at"),
        ("updated_at_in_seconds", "updated_at"),
    ),
    "m8flow_connector_configuration": (
        ("created_at_in_seconds", "created_at"),
        ("updated_at_in_seconds", "updated_at"),
    ),
    "m8flow_tenant_invitation": (
        ("created_at_in_seconds", "created_at"),
        ("updated_at_in_seconds", "updated_at"),
    ),
    "m8flow_external_form_requests": (
        ("created_at_in_seconds", "created_at"),
        ("updated_at_in_seconds", "updated_at"),
    ),
}

EPOCH_COLUMNS: dict[str, tuple[str, ...]] = {
    table: tuple(legacy for legacy, _native in pairs)
    for table, pairs in TIMESTAMP_COLUMNS.items()
    if table != "process_instance_event"
}


def _bind():
    return op.get_bind()


def _inspector():
    return sa.inspect(_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _columns(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _quote_identifier(identifier: str) -> str:
    return _bind().dialect.identifier_preparer.quote(identifier)


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _table_exists(table_name) and column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _add_timestamp_columns() -> None:
    for table_name, pairs in TIMESTAMP_COLUMNS.items():
        for _legacy_name, native_name in pairs:
            _add_column_if_missing(
                table_name,
                sa.Column(native_name, sa.DateTime(timezone=True), nullable=True),
            )

    # Core 0.2.0 intentionally widens the legacy epoch fields so dates after
    # 2038 remain representable.  Avoid rebuilding already-upgraded tables.
    for table_name, column_names in EPOCH_COLUMNS.items():
        if not _table_exists(table_name):
            continue
        reflected = {
            column["name"]: column["type"]
            for column in _inspector().get_columns(table_name)
        }
        columns_to_widen = [
            name
            for name in column_names
            if name in reflected and reflected[name].__class__.__name__.lower() != "biginteger"
        ]
        if not columns_to_widen:
            continue
        if _bind().dialect.name == "sqlite":
            with op.batch_alter_table(table_name, recreate="always") as batch_op:
                for name in columns_to_widen:
                    batch_op.alter_column(name, type_=sa.BigInteger())
        else:
            for name in columns_to_widen:
                op.alter_column(
                    table_name,
                    name,
                    existing_type=reflected[name],
                    type_=sa.BigInteger(),
                )

    dialect = _bind().dialect.name
    for table_name, pairs in TIMESTAMP_COLUMNS.items():
        if not _table_exists(table_name):
            continue
        for legacy_name, native_name in pairs:
            if legacy_name not in _columns(table_name) or native_name not in _columns(table_name):
                continue
            expression = _epoch_to_datetime_expression(dialect, legacy_name)
            quoted_table = _quote_identifier(table_name)
            op.execute(
                sa.text(
                    f"UPDATE {quoted_table} SET {_quote_identifier(native_name)} = {expression} "
                    f"WHERE {_quote_identifier(native_name)} IS NULL "
                    f"AND {_quote_identifier(legacy_name)} IS NOT NULL"
                )
            )


def _epoch_to_datetime_expression(dialect: str, legacy_name: str) -> str:
    """Return the database expression used to convert an epoch value."""
    if dialect == "sqlite":
        return f"datetime({legacy_name}, 'unixepoch')"
    if dialect == "postgresql":
        return f"to_timestamp({legacy_name})"
    if dialect in {"mysql", "mariadb"}:
        return f"FROM_UNIXTIME({legacy_name})"
    raise RuntimeError(f"Unsupported database dialect for timestamp conversion: {dialect}")


def _create_work_item() -> None:
    if not _table_exists("human_task") or _table_exists("work_item"):
        return

    op.create_table(
        "work_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_instance_id", sa.Integer(), nullable=False),
        sa.Column("task_guid", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=50), nullable=True),
        sa.Column("lane_assignment_id", sa.Integer(), nullable=True),
        sa.Column("completed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("actual_owner_id", sa.Integer(), nullable=True),
        sa.Column("task_status", sa.String(length=50), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.BigInteger(), nullable=True),
        sa.Column("created_at_in_seconds", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"], ["human_task.id"], name="m8f_work_item_human_task_fk", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"], name="m8f_work_item_tenant_fk"),
        sa.ForeignKeyConstraint(["process_instance_id"], ["process_instance.id"], name="m8f_work_item_process_instance_fk"),
        sa.ForeignKeyConstraint(["task_guid"], ["task.guid"], name="m8f_work_item_task_fk"),
        sa.ForeignKeyConstraint(["lane_assignment_id"], ["group.id"], name="m8f_work_item_lane_group_fk"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["user.id"], name="m8f_work_item_completed_by_user_fk"),
        sa.ForeignKeyConstraint(["actual_owner_id"], ["user.id"], name="m8f_work_item_actual_owner_fk"),
        sa.PrimaryKeyConstraint("id", name="m8f_work_item_pk"),
    )
    for index_name, columns in (
        ("ix_work_item_m8f_tenant_id", ["m8f_tenant_id"]),
        ("ix_work_item_process_instance_id", ["process_instance_id"]),
        ("ix_work_item_task_guid", ["task_guid"]),
        ("ix_work_item_lane_assignment_id", ["lane_assignment_id"]),
        ("ix_work_item_completed_by_user_id", ["completed_by_user_id"]),
        ("ix_work_item_actual_owner_id", ["actual_owner_id"]),
        ("ix_work_item_completed", ["completed"]),
    ):
        op.create_index(index_name, "work_item", columns, unique=False)

    op.execute(
        sa.text(
            "INSERT INTO work_item ("
            "id, process_instance_id, task_guid, task_id, lane_assignment_id, "
            "completed_by_user_id, actual_owner_id, task_status, completed, "
            "updated_at_in_seconds, created_at_in_seconds, updated_at, created_at, "
            "m8f_tenant_id) "
            "SELECT id, process_instance_id, task_guid, task_id, lane_assignment_id, "
            "completed_by_user_id, actual_owner_id, task_status, completed, "
            "updated_at_in_seconds, created_at_in_seconds, updated_at, created_at, "
            "m8f_tenant_id FROM human_task"
        )
    )
    _ensure_tenant_rls("work_item")


def _ensure_tenant_rls(table_name: str) -> None:
    if _bind().dialect.name != "postgresql" or not _table_exists(table_name):
        return
    tenant_policy = f"{table_name}_tenant_isolation"
    bypass_policy = f"{table_name}_super_admin_select"
    op.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {tenant_policy} ON {table_name}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {tenant_policy} ON {table_name} FOR ALL "
            f"USING {_TENANT_RLS_PREDICATE} WITH CHECK {_TENANT_RLS_PREDICATE}"
        )
    )
    op.execute(sa.text(f"DROP POLICY IF EXISTS {bypass_policy} ON {table_name}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {bypass_policy} ON {table_name} FOR SELECT "
            f"USING {_BYPASS_RLS_PREDICATE}"
        )
    )


def _tenant_scope_json_data() -> None:
    if not _table_exists("json_data") or "m8f_tenant_id" in _columns("json_data"):
        _ensure_tenant_rls("json_data")
        return

    bind = _bind()
    json_rows = {
        str(row[0]).strip(): row[1]
        for row in bind.execute(sa.text("SELECT hash, data FROM json_data"))
    }
    references = list(
        bind.execute(
            sa.text(
                "SELECT DISTINCT m8f_tenant_id, payload_hash FROM ("
                "SELECT m8f_tenant_id, json_data_hash AS payload_hash FROM bpmn_process "
                "WHERE json_data_hash IS NOT NULL "
                "UNION ALL SELECT m8f_tenant_id, json_data_hash AS payload_hash FROM task "
                "WHERE json_data_hash IS NOT NULL "
                "UNION ALL SELECT m8f_tenant_id, python_env_data_hash AS payload_hash FROM task "
                "WHERE python_env_data_hash IS NOT NULL"
                ") AS json_reference_sources"
            )
        )
    )

    reference_tenants: dict[str, set[str]] = {}
    invalid_references: list[str] = []
    for tenant_id, payload_hash in references:
        if tenant_id is None or payload_hash is None:
            invalid_references.append(f"tenant={tenant_id!r}, hash={payload_hash!r}")
            continue
        normalized_tenant_id = str(tenant_id).strip()
        normalized_payload_hash = str(payload_hash).strip()
        reference_tenants.setdefault(normalized_payload_hash, set()).add(normalized_tenant_id)

    missing_payloads = sorted(set(reference_tenants) - set(json_rows))
    unreferenced_payloads = sorted(set(json_rows) - set(reference_tenants))
    referenced_tenants = {tenant_id for tenant_ids in reference_tenants.values() for tenant_id in tenant_ids}
    known_tenants = {
        str(row[0]).strip() for row in bind.execute(sa.text("SELECT id FROM m8flow_tenant"))
    }
    missing_tenants = sorted(referenced_tenants - known_tenants)
    errors: list[str] = []
    if invalid_references:
        errors.append("null tenant or payload reference: " + ", ".join(invalid_references[:5]))
    if missing_payloads:
        errors.append("referenced payload hashes are missing from json_data: " + ", ".join(missing_payloads[:5]))
    if unreferenced_payloads:
        errors.append("json_data rows have no tenant-qualified reference: " + ", ".join(unreferenced_payloads[:5]))
    if missing_tenants:
        errors.append("referenced tenants are missing from m8flow_tenant: " + ", ".join(missing_tenants[:5]))
    if errors:
        raise RuntimeError("Cannot safely tenant-scope json_data; no payload rows were re-keyed. " + " | ".join(errors))

    stage_table = "m8f_json_data_tenant_scope_stage"
    if _table_exists(stage_table):
        op.drop_table(stage_table)
    op.create_table(
        stage_table,
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("hash", sa.String(length=255), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"], name="m8f_json_data_tenant_fk"),
        sa.PrimaryKeyConstraint("m8f_tenant_id", "hash", name="m8f_json_data_tenant_hash_pk"),
    )
    for payload_hash, tenant_ids in reference_tenants.items():
        for tenant_id in sorted(tenant_ids):
            bind.execute(
                sa.text(
                    f"INSERT INTO {stage_table} (m8f_tenant_id, hash, data) "
                    "VALUES (:tenant_id, :payload_hash, :data)"
                ).bindparams(sa.bindparam("data", type_=sa.JSON)),
                {"tenant_id": tenant_id, "payload_hash": payload_hash, "data": json_rows[payload_hash]},
            )
    op.drop_table("json_data")
    op.rename_table(stage_table, "json_data")
    _ensure_tenant_rls("json_data")


def _unique_names(table_name: str) -> set[str | None]:
    return {item.get("name") for item in _inspector().get_unique_constraints(table_name)}


def _index_names(table_name: str) -> set[str | None]:
    names = {item.get("name") for item in _inspector().get_indexes(table_name)}
    # SQLAlchemy intentionally skips SQLite expression indexes during
    # reflection. The 0.2.0 metadata creates those indexes on a fresh
    # database, so consult SQLite's catalog as a fallback before attempting to
    # create them again.
    if _bind().dialect.name == "sqlite" and _table_exists(table_name):
        names.update(
            row[0]
            for row in _bind()
            .execute(
                sa.text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'index' AND tbl_name = :table_name"
                ),
                {"table_name": table_name},
            )
            if row[0]
        )
    return names


def _check_names(table_name: str) -> set[str | None]:
    return {item.get("name") for item in _inspector().get_check_constraints(table_name)}


def _queue_sqlite_table_operation(table_name: str, operation: Callable[[Any], None]) -> None:
    _SQLITE_PENDING_TABLE_OPERATIONS.setdefault(table_name, []).append(operation)


def _flush_sqlite_table_operations() -> None:
    if _bind().dialect.name != "sqlite":
        return
    try:
        for table_name, operations in _SQLITE_PENDING_TABLE_OPERATIONS.items():
            if not _table_exists(table_name):
                continue
            with op.batch_alter_table(table_name, recreate="always") as batch_op:
                for operation in operations:
                    operation(batch_op)
    finally:
        _SQLITE_PENDING_TABLE_OPERATIONS.clear()
        _SQLITE_PENDING_CONSTRAINTS.clear()


def _add_unique_constraint_if_missing(table_name: str, name: str, columns: list[str]) -> None:
    if not _table_exists(table_name) or name in _unique_names(table_name):
        return
    if _bind().dialect.name == "postgresql":
        op.create_unique_constraint(name, table_name, columns)
    elif _bind().dialect.name == "sqlite":
        key = (table_name, name)
        if key not in _SQLITE_PENDING_CONSTRAINTS:
            _SQLITE_PENDING_CONSTRAINTS.add(key)
            _queue_sqlite_table_operation(
                table_name,
                lambda batch_op, constraint_name=name, constraint_columns=columns: batch_op.create_unique_constraint(
                    constraint_name, constraint_columns
                ),
            )
    else:
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.create_unique_constraint(name, columns)


def _add_check_constraint_if_missing(table_name: str, name: str, sql: str) -> None:
    if not _table_exists(table_name) or name in _check_names(table_name):
        return
    if _bind().dialect.name == "postgresql":
        op.create_check_constraint(name, table_name, sql)
    elif _bind().dialect.name == "sqlite":
        key = (table_name, name)
        if key not in _SQLITE_PENDING_CONSTRAINTS:
            _SQLITE_PENDING_CONSTRAINTS.add(key)
            _queue_sqlite_table_operation(
                table_name,
                lambda batch_op, constraint_name=name, constraint_sql=sql: batch_op.create_check_constraint(
                    constraint_name, constraint_sql
                ),
            )
    else:
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.create_check_constraint(name, sql)


def _rename_constraints() -> None:
    renames = (
        ("user", "service_key", "m8f_user_service_id_key", "unique"),
        ("bpmn_process_definition", "bpmn_process_definition_full_process_model_hash_tenant_unique", "m8f_bpmn_process_definition_full_process_model_hash_tenant_key", "unique"),
        ("bpmn_process_definition", "process_hash_unique", "m8f_bpmn_process_definition_process_hash_key", "unique"),
        ("permission_target", "permission_target_uri_command_unique", "m8f_permission_target_uri_command_key", "unique"),
        ("permission_assignment", "permission_assignment_unique", "m8f_permission_assignment_principal_target_permission_key", "unique"),
        ("user_group_assignment", "user_group_assignment_unique", "m8f_user_group_assignment_user_group_key", "unique"),
        ("task_definition", "task_definition_unique", "m8f_task_definition_tenant_process_key", "unique"),
        ("human_task_user", "human_task_user_unique", "m8f_human_task_user_key", "unique"),
        ("process_instance_metadata", "process_instance_metadata_unique", "m8f_process_instance_metadata_key", "unique"),
        ("future_task", "future_task_task_guid_fk", "m8f_future_task_task_guid_fk", "foreignkey"),
    )
    for table_name, old_name, new_name, kind in renames:
        if not _table_exists(table_name):
            continue
        inspector = _inspector()
        if kind == "unique":
            constraints = inspector.get_unique_constraints(table_name)
        else:
            constraints = inspector.get_foreign_keys(table_name)
        old = next((item for item in constraints if item.get("name") == old_name), None)
        if old is None or new_name in ({item.get("name") for item in constraints}):
            continue
        if _bind().dialect.name == "postgresql":
            op.drop_constraint(old_name, table_name, type_=kind)
            if kind == "unique":
                op.create_unique_constraint(new_name, table_name, old["column_names"])
            else:
                op.create_foreign_key(
                    new_name,
                    table_name,
                    old["referred_table"],
                    old["constrained_columns"],
                    old["referred_columns"],
                    ondelete=(old.get("options") or {}).get("ondelete"),
                )
        elif _bind().dialect.name == "sqlite":
            def rename_constraint(
                batch_op: Any,
                *,
                old_constraint_name: str = old_name,
                new_constraint_name: str = new_name,
                constraint_kind: str = kind,
                constraint: dict[str, Any] = old,
            ) -> None:
                batch_op.drop_constraint(old_constraint_name, type_=constraint_kind)
                if constraint_kind == "unique":
                    batch_op.create_unique_constraint(new_constraint_name, constraint["column_names"])
                else:
                    batch_op.create_foreign_key(
                        new_constraint_name,
                        constraint["referred_table"],
                        constraint["constrained_columns"],
                        constraint["referred_columns"],
                        ondelete=(constraint.get("options") or {}).get("ondelete"),
                    )

            _queue_sqlite_table_operation(table_name, rename_constraint)
        else:
            with op.batch_alter_table(table_name, recreate="always") as batch_op:
                batch_op.drop_constraint(old_name, type_=kind)
                if kind == "unique":
                    batch_op.create_unique_constraint(new_name, old["column_names"])
                else:
                    batch_op.create_foreign_key(
                        new_name,
                        old["referred_table"],
                        old["constrained_columns"],
                        old["referred_columns"],
                        ondelete=(old.get("options") or {}).get("ondelete"),
                    )


def _create_authorization_indexes() -> None:
    if _table_exists("group") and "ix_group_authorization_key" not in _index_names("group"):
        op.create_index("ix_group_authorization_key", "group", ["authorization_key"], unique=False)

    if not _table_exists("permission_target"):
        return
    for index_name, column_name in (
        ("ix_permission_target_resource_type", "resource_type"),
        ("ix_permission_target_resource_id", "resource_id"),
    ):
        if index_name not in _index_names("permission_target"):
            op.create_index(index_name, "permission_target", [column_name], unique=False)

    if _bind().dialect.name not in {"postgresql", "sqlite"}:
        return
    if "uri" in _columns("permission_target") and "m8f_permission_target_uri_command_identity_key" not in _index_names("permission_target"):
        op.create_index(
            "m8f_permission_target_uri_command_identity_key",
            "permission_target",
            ["uri", sa.text("COALESCE(command, '')")],
            unique=True,
        )
    if "m8f_permission_target_resource_command_identity_key" not in _index_names("permission_target"):
        op.create_index(
            "m8f_permission_target_resource_command_identity_key",
            "permission_target",
            ["resource_type", "resource_id", sa.text("COALESCE(command, '')")],
            unique=True,
            postgresql_where=sa.text("resource_type IS NOT NULL AND resource_id IS NOT NULL"),
            sqlite_where=sa.text("resource_type IS NOT NULL AND resource_id IS NOT NULL"),
        )


def _authorization_schema() -> None:
    if _table_exists("group") and "authorization_key" not in _columns("group"):
        op.add_column("group", sa.Column("authorization_key", sa.String(length=255), nullable=True))
    if _table_exists("group"):
        group_columns = _columns("group")
        select_columns = "id, identifier"
        if "source_is_open_id" in group_columns:
            select_columns += ", source_is_open_id"
        rows = _bind().execute(
            sa.text(f'SELECT {select_columns} FROM "group" WHERE authorization_key IS NULL')
        ).all()
        # Workflow lane groups are local, non-IdP groups. They intentionally
        # may share an identifier with the tenant RBAC group (for example,
        # ``m8flow:Submitters``), so their authorization keys must be based on
        # their stable row id rather than the shared identifier. Duplicate
        # identifiers remain invalid only among actual IdP/RBAC groups.
        has_source_column = "source_is_open_id" in group_columns
        rbac_identifiers = [
            str(row[1])
            for row in rows
            if row[1] and (not has_source_column or bool(row[2]))
        ]
        if len(rbac_identifiers) != len(set(rbac_identifiers)):
            raise RuntimeError(
                "Cannot backfill unique group authorization keys: duplicate RBAC group identifiers exist"
            )
        for row in rows:
            group_id, identifier = row[0], row[1]
            source_is_open_id = bool(row[2]) if has_source_column else True
            key = (
                f"authorization:{identifier or group_id}"
                if source_is_open_id
                else f"authorization:lane:{group_id}"
            )
            _bind().execute(sa.text('UPDATE "group" SET authorization_key = :key WHERE id = :id'), {"key": key, "id": group_id})
        _add_unique_constraint_if_missing("group", "m8f_group_authorization_key", ["authorization_key"])

    if _table_exists("permission_target"):
        _add_column_if_missing("permission_target", sa.Column("resource_type", sa.String(length=100), nullable=True))
        _add_column_if_missing("permission_target", sa.Column("resource_id", sa.String(length=255), nullable=True))
        duplicates = _bind().execute(
            sa.text(
                "SELECT resource_type, resource_id, COALESCE(command, '') FROM permission_target "
                "WHERE resource_type IS NOT NULL AND resource_id IS NOT NULL "
                "GROUP BY resource_type, resource_id, COALESCE(command, '') HAVING COUNT(*) > 1"
            )
        ).all()
        if duplicates:
            raise RuntimeError(f"Cannot enforce unique permission resource identities; duplicates: {duplicates}")
        _add_unique_constraint_if_missing(
            "permission_target", "m8f_permission_target_resource_command_key", ["resource_type", "resource_id", "command"]
        )
        invalid_rows = _bind().execute(
            sa.text(
                "SELECT id FROM permission_target "
                "WHERE (resource_type IS NULL) <> (resource_id IS NULL) ORDER BY id"
            )
        ).scalars().all()
        if invalid_rows:
            raise RuntimeError(f"Cannot enforce complete permission resource pairs; invalid rows: {invalid_rows}")
        _add_check_constraint_if_missing(
            "permission_target",
            "m8f_permission_target_resource_pair_check",
            "(resource_type IS NULL AND resource_id IS NULL) OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)",
        )

        # PostgreSQL and SQLite can normalize NULL command values in an
        # expression index. MySQL keeps the existing unique constraint because
        # functional-index syntax and NULL semantics vary by supported version.
        if _bind().dialect.name in {"postgresql", "sqlite"} and "uri" in _columns("permission_target"):
            uri_duplicates = _bind().execute(
                sa.text(
                    "SELECT uri, COALESCE(command, '') FROM permission_target "
                    "GROUP BY uri, COALESCE(command, '') HAVING COUNT(*) > 1"
                )
            ).all()
            if uri_duplicates:
                raise RuntimeError(f"Cannot enforce unique permission target URI identities; duplicates: {uri_duplicates}")

    _rename_constraints()
    _add_check_constraint_if_missing(
        "principal",
        "m8f_principal_exactly_one_subject",
        "(user_id IS NOT NULL AND group_id IS NULL) OR (user_id IS NULL AND group_id IS NOT NULL)",
    )
    _flush_sqlite_table_operations()
    _create_authorization_indexes()


def _event_category() -> None:
    if not _table_exists("process_instance_event"):
        return
    if "category" not in _columns("process_instance_event"):
        op.add_column("process_instance_event", sa.Column("category", sa.String(length=20), nullable=True))
    op.execute(
        sa.text(
            "UPDATE process_instance_event SET category = CASE "
            "WHEN event_type LIKE 'task_%' THEN 'task' ELSE 'process' END "
            "WHERE category IS NULL"
        )
    )
    if "ix_process_instance_event_category" not in _index_names("process_instance_event"):
        op.create_index("ix_process_instance_event_category", "process_instance_event", ["category"], unique=False)


def upgrade() -> None:
    _add_timestamp_columns()
    _create_work_item()
    _event_category()
    _tenant_scope_json_data()
    _authorization_schema()


def downgrade() -> None:
    """Remove the additive compatibility table before the root teardown.

    The tenant-scoped JSON re-key cannot be safely collapsed back to the old
    global ``hash`` primary key: one payload may now legitimately exist for
    multiple tenants. It therefore remains in place for backup-based rollback.
    ``work_item`` is additive and can be removed because its legacy
    ``human_task`` rows remain available to the compatibility layer.
    """
    if _table_exists("work_item"):
        if _bind().dialect.name == "postgresql":
            op.execute(sa.text("DROP POLICY IF EXISTS work_item_tenant_isolation ON work_item"))
            op.execute(sa.text("DROP POLICY IF EXISTS work_item_super_admin_select ON work_item"))
        op.drop_table("work_item")
