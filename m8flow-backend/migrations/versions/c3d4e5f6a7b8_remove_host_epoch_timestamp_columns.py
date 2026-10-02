"""Remove legacy epoch timestamp columns from M8Flow-owned tables.

The core-owned tables retain their ``*_in_seconds`` compatibility columns until
the corresponding m8flow-bpmn-core migration is applied.  This revision only
changes tables declared by ``HostBase``.  The native timezone-aware columns were
added and backfilled by ``b2c3d4e5f6a7`` before this destructive cleanup. The
cleanup also repairs an older ``b2`` schema when a legacy column exists
without its native counterpart.

The downgrade restores nullable columns for schema round-trips, but cannot
restore the original epoch values. Restore a database backup to recover those
historical values.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


# Keep this list explicit.  The core tables deliberately do not appear here;
# their cleanup will be delivered by m8flow-bpmn-core.
HOST_LEGACY_TIMESTAMP_COLUMNS: dict[str, tuple[str, ...]] = {
    "secret": ("created_at_in_seconds", "updated_at_in_seconds"),
    "pkce_code_verifier": ("created_at_in_seconds",),
    "refresh_token": ("created_at_in_seconds", "updated_at_in_seconds"),
    "service_account": ("created_at_in_seconds",),
    "task_draft_data": ("created_at_in_seconds", "updated_at_in_seconds"),
    "task_instructions_for_end_user": ("created_at_in_seconds",),
    "api_log": ("created_at_in_seconds",),
    "process_instance_file_data": ("created_at_in_seconds",),
    "m8flow_templates": ("created_at_in_seconds", "updated_at_in_seconds"),
    "m8flow_process_model_template": ("created_at_in_seconds", "updated_at_in_seconds"),
    "m8flow_nats_api_key": ("created_at_in_seconds",),
    "m8flow_external_form_requests": ("created_at_in_seconds", "updated_at_in_seconds"),
    "m8flow_tenant_invitation": ("created_at_in_seconds", "updated_at_in_seconds"),
    "m8flow_connector_configuration": ("created_at_in_seconds", "updated_at_in_seconds"),
}


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _quote_identifier(identifier: str) -> str:
    return op.get_bind().dialect.identifier_preparer.quote(identifier)


def _add_native_columns(table_name: str, native_columns: tuple[str, ...]) -> None:
    definitions = [sa.Column(column, sa.DateTime(timezone=True), nullable=True) for column in native_columns]
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            for definition in definitions:
                batch_op.add_column(definition)
        return

    for definition in definitions:
        op.add_column(table_name, definition)


def _backfill_native_columns(table_name: str, legacy_columns: tuple[str, ...]) -> None:
    dialect = op.get_bind().dialect.name
    quoted_table = _quote_identifier(table_name)
    for legacy_column in legacy_columns:
        native_column = legacy_column.removesuffix("_in_seconds")
        quoted_legacy = _quote_identifier(legacy_column)
        quoted_native = _quote_identifier(native_column)
        if dialect == "sqlite":
            expression = f"datetime({quoted_legacy}, 'unixepoch')"
        elif dialect == "postgresql":
            expression = f"to_timestamp({quoted_legacy})"
        elif dialect in {"mysql", "mariadb"}:
            expression = f"FROM_UNIXTIME({quoted_legacy})"
        else:
            raise RuntimeError(f"Unsupported database dialect for timestamp conversion: {dialect}")
        op.execute(
            sa.text(
                f"UPDATE {quoted_table} SET {quoted_native} = {expression} "
                f"WHERE {quoted_native} IS NULL AND {quoted_legacy} IS NOT NULL"
            )
        )


def _drop_columns(table_name: str, columns: tuple[str, ...]) -> None:
    table_columns = _columns(table_name)
    existing = [column for column in columns if column in table_columns]
    if not existing:
        return

    missing_native = [
        column.removesuffix("_in_seconds")
        for column in existing
        if column.removesuffix("_in_seconds") not in table_columns
    ]
    if missing_native:
        _add_native_columns(table_name, tuple(missing_native))
        _backfill_native_columns(table_name, tuple(existing))

    # SQLite requires table recreation for reliable multi-column drops.  The
    # batch operation is also harmless for a table with one legacy column.
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            for column in existing:
                batch_op.drop_column(column)
        return

    for column in existing:
        op.drop_column(table_name, column)


def _add_columns(table_name: str, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in _columns(table_name)]
    if not missing:
        return

    definitions = [sa.Column(column, sa.BigInteger(), nullable=True) for column in missing]
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            for definition in definitions:
                batch_op.add_column(definition)
        return

    for definition in definitions:
        op.add_column(table_name, definition)


def upgrade() -> None:
    for table_name, columns in HOST_LEGACY_TIMESTAMP_COLUMNS.items():
        _drop_columns(table_name, columns)


def downgrade() -> None:
    # The column shape can be restored for Alembic structure round-trips, but
    # the original values cannot be reconstructed exactly after conversion to
    # timezone-aware datetimes. Production rollback must use a database
    # backup if those values are required.
    for table_name, columns in HOST_LEGACY_TIMESTAMP_COLUMNS.items():
        _add_columns(table_name, columns)
