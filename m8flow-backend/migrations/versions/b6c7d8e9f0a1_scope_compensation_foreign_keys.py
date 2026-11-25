"""Scope compensation journal references to their tenant.

Revision ID: b6c7d8e9f0a1
Revises: a3f4e5d6c7b8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b6c7d8e9f0a1"
down_revision = "a3f4e5d6c7b8"
branch_labels = None
depends_on = None

JOURNAL_TABLES = ("compensation_scope", "compensation_run", "compensation_record")
_PROCESS_INSTANCE_KEY = ("m8f_tenant_id", "id")
_COMPOSITE_FK_COLUMNS = ("m8f_tenant_id", "process_instance_id")
_LEGACY_FK_COLUMNS = ("process_instance_id",)
_SQLITE_FK_NAMING = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _validate_process_instance_tenant_key(
    bind: sa.Connection, *, table_name: str = "process_instance"
) -> None:
    """Require an exact, non-partial unique key for the composite FK target."""
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        raise RuntimeError(
            "Cannot scope compensation journal references: required table "
            f"{table_name!r} is missing. Upgrade the core schema first."
        )

    def compatible(columns: list[str] | tuple[str, ...] | None) -> bool:
        return columns is not None and len(columns) == 2 and set(columns) == set(_PROCESS_INSTANCE_KEY)

    def partial(index: dict) -> bool:
        if index.get("where") is not None or index.get("filter_definition") is not None:
            return True
        return any(
            key.casefold().endswith("_where") and predicate is not None
            for key, predicate in (index.get("dialect_options") or {}).items()
        )

    keys = [inspector.get_pk_constraint(table_name).get("constrained_columns")]
    keys.extend(item.get("column_names") for item in inspector.get_unique_constraints(table_name))
    keys.extend(
        item.get("column_names")
        for item in inspector.get_indexes(table_name)
        if item.get("unique") and item.get("column_names") and not partial(item)
    )
    if not any(compatible(columns) for columns in keys):
        raise RuntimeError(
            "Cannot scope compensation journal references: process_instance must have a "
            "primary key, unique constraint, or non-partial unique index covering exactly "
            "(m8f_tenant_id, id). Restore a schema-level unique key on those columns, "
            "then rerun the migration."
        )


def _foreign_keys(table: str) -> list[dict]:
    return sa.inspect(op.get_bind()).get_foreign_keys(table)


def _is_reference(foreign_key: dict, columns: tuple[str, ...], referred: tuple[str, ...]) -> bool:
    return (
        foreign_key.get("referred_table") == "process_instance"
        and tuple(foreign_key.get("constrained_columns") or ()) == columns
        and tuple(foreign_key.get("referred_columns") or ()) == referred
    )


def _sqlite_constraint_name(table: str, columns: tuple[str, ...]) -> str:
    # The historical journal migration created the single-column FK unnamed.
    # Alembic applies this convention when reflecting unnamed SQLite FKs into
    # batch mode, allowing the constraint to be replaced without rebuilding
    # table contents in application code.
    return f"fk_{table}_{columns[0]}_process_instance"


def _replace_reference(table: str, *, upgrade: bool) -> None:
    if not sa.inspect(op.get_bind()).has_table(table):
        return

    foreign_keys = _foreign_keys(table)
    composite = [
        fk for fk in foreign_keys
        if _is_reference(fk, _COMPOSITE_FK_COLUMNS, _PROCESS_INSTANCE_KEY)
    ]
    legacy = [
        fk for fk in foreign_keys
        if _is_reference(fk, _LEGACY_FK_COLUMNS, ("id",))
    ]

    if upgrade:
        desired_present = bool(composite)
        to_remove = legacy
        create_name = f"fk_{table}_m8f_tenant_id_process_instance"
        create_columns = list(_COMPOSITE_FK_COLUMNS)
        referred_columns = list(_PROCESS_INSTANCE_KEY)
    else:
        desired_present = bool(legacy)
        to_remove = composite
        create_name = f"fk_{table}_process_instance_id_process_instance"
        create_columns = list(_LEGACY_FK_COLUMNS)
        referred_columns = ["id"]

    if not to_remove and desired_present:
        return

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table, naming_convention=_SQLITE_FK_NAMING) as batch:
            for foreign_key in to_remove:
                columns = tuple(foreign_key.get("constrained_columns") or ())
                batch.drop_constraint(
                    foreign_key.get("name") or _sqlite_constraint_name(table, columns),
                    type_="foreignkey",
                )
            if not desired_present:
                batch.create_foreign_key(
                    create_name,
                    "process_instance",
                    create_columns,
                    referred_columns,
                )
        return

    if not desired_present:
        op.create_foreign_key(
            create_name,
            table,
            "process_instance",
            create_columns,
            referred_columns,
        )
    for foreign_key in to_remove:
        name = foreign_key.get("name")
        if not name:
            raise RuntimeError(
                f"Cannot replace an unnamed foreign key on {table!r}; "
                "name the constraint before rerunning the migration."
            )
        op.drop_constraint(name, table, type_="foreignkey")


def upgrade() -> None:
    bind = op.get_bind()
    _validate_process_instance_tenant_key(bind)
    for table in JOURNAL_TABLES:
        _replace_reference(table, upgrade=True)


def downgrade() -> None:
    for table in JOURNAL_TABLES:
        _replace_reference(table, upgrade=False)
