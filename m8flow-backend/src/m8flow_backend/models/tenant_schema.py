# m8flow-backend/src/m8flow_backend/models/tenant_schema.py
"""m8flow's complete schema delta over upstream SpiffArena, in one place.

WHY THIS EXISTS
---------------
m8flow used to express its schema changes by copying each upstream model file
and editing it.  That put LGPL-2.1 upstream code inside the Apache-2.0 tree.

Instead, this module registers a single SQLAlchemy DDL listener that applies
m8flow's changes to upstream's tables as they are constructed.  Upstream's own
mapped classes then carry m8flow's columns and constraints, so no model file
needs to be copied or overridden at all.

WHAT IT DOES
------------
* adds ``m8f_tenant_id`` to the 36 tenant-scoped upstream tables
* adds the two m8flow-only columns that live on upstream tables
* widens composite UNIQUE constraints to include the tenant column
* relaxes upstream's global single-column UNIQUE to per-tenant uniqueness
* adds m8flow-specific constraints and drops indexes m8flow does not want

READ THIS BEFORE CHANGING A MODEL
---------------------------------
Nothing in ``m8flow_backend/models/`` shadows upstream any more.  If you need a
schema change on an upstream table, add it here - do not copy the upstream file.

ORDERING REQUIREMENT
--------------------
``register()`` must run before any model module is imported.  ``assert_applied()``
turns a mistake into a loud boot failure instead of a missing column at runtime.
"""
from __future__ import annotations

import logging

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy import UniqueConstraint
from sqlalchemy import event

LOGGER = logging.getLogger(__name__)

TENANT_COLUMN = "m8f_tenant_id"
TENANT_FK = "m8flow_tenant.id"


# ---------------------------------------------------------------------------
# Configuration - the complete m8flow schema delta
# ---------------------------------------------------------------------------

#: Upstream tables that gain ``m8f_tenant_id``.
#: NOTE: ``user``, ``permission_target`` and ``permission_assignment`` are
#: deliberately absent - users and permissions are shared across tenants.
TENANT_TABLES: frozenset[str] = frozenset(
    {
        "api_log",
        "bpmn_process",
        "bpmn_process_definition",
        "bpmn_process_definition_relationship",
        "configuration",
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
        "pkce_code_verifier",
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
        "refresh_token",
        "secret",
        "service_account",
        "task",
        "task_definition",
        "task_draft_data",
        "task_instructions_for_end_user",
        "typeahead",
    }
)

#: m8flow-only columns on upstream tables, beyond the tenant column.
#: Factories, because a Column instance cannot be attached to two tables.
EXTRA_COLUMNS: dict[str, list] = {
    "process_instance": [
        lambda: Column(
            "bpmn_version_id",
            Integer,
            ForeignKey("process_model_bpmn_version.id"),
            nullable=True,
            index=True,
        ),
    ],
    "permission_target": [
        lambda: Column("command", String(255), nullable=True),
    ],
}

#: Existing upstream composite UNIQUE constraints that must include the tenant
#: column.  ``{table: (constraint_name, upstream_columns)}``
WIDEN_UNIQUE: dict[str, tuple[str, list[str]]] = {
    "bpmn_process_definition": (
        "process_hash_unique",
        ["full_process_model_hash", "single_process_hash"],
    ),
    "json_data_store": ("_identifier_location_unique", ["identifier", "location"]),
    "kkv_data_store": ("_kkv_identifier_location_unique", ["identifier", "location"]),
    "message": ("message_identifier_location_unique", ["identifier", "location"]),
    "process_instance_report": (
        "process_instance_report_unique",
        ["created_by_id", "identifier"],
    ),
    "reference_cache": (
        "reference_cache_uniq",
        ["generation_id", "identifier", "relative_location", "type"],
    ),
    "service_account": ("service_account_uniq", ["name", "created_by_user_id"]),
    "task_definition": (
        "task_definition_unique",
        ["bpmn_process_definition_id", "bpmn_identifier"],
    ),
}

#: Constraints m8flow adds that upstream does not have at all.
#: ``{table: [(name, columns), ...]}``
ADD_UNIQUE: dict[str, list[tuple[str, list[str]]]] = {
    "bpmn_process_definition": [
        (
            "bpmn_process_definition_full_process_model_hash_tenant_unique",
            [TENANT_COLUMN, "full_process_model_hash"],
        )
    ],
    "message_triggerable_process_model": [
        (
            "message_triggerable_process_model_message_name_tenant_unique",
            [TENANT_COLUMN, "message_name"],
        )
    ],
    "pkce_code_verifier": [
        ("pkce_code_verifier_pkce_id_tenant_unique", [TENANT_COLUMN, "pkce_id"])
    ],
    "refresh_token": [
        ("refresh_token_user_id_tenant_unique", [TENANT_COLUMN, "user_id"])
    ],
    "secret": [("secret_key_tenant_unique", [TENANT_COLUMN, "key"])],
    "permission_target": [("permission_target_uri_command_unique", ["uri", "command"])],
    "permission_assignment": [
        (
            "permission_assignment_unique",
            ["principal_id", "permission_target_id", "permission"],
        )
    ],
}

#: Upstream single-column ``unique=True`` that must become per-tenant (or, for
#: ``user`` and ``permission_target``, simply non-unique).  An index replaces it
#: so lookups stay fast.
RELAX_UNIQUE: dict[str, list[str]] = {
    "bpmn_process_definition": ["full_process_model_hash"],
    "message_triggerable_process_model": ["message_name"],
    "permission_target": ["uri"],
    "pkce_code_verifier": ["pkce_id"],
    "refresh_token": ["user_id"],
    "secret": ["key"],
    "user": ["username"],
}

#: Upstream constraints m8flow replaces with its own (see ADD_UNIQUE).
#: Without this the table ends up carrying both.
DROP_UNIQUE_BY_NAME: dict[str, list[str]] = {
    "permission_assignment": ["permission_assignment_uniq"],
}

#: Indexes upstream declares that m8flow drops (covered by composite constraints).
DROP_INDEX: dict[str, list[str]] = {
    "permission_assignment": ["principal_id", "permission_target_id"],
}

#: Explicit indexes m8flow adds.
ADD_INDEX: dict[str, list[str]] = {
    "permission_target": ["uri", "command"],
}

#: Every table this module touches - used by assert_applied().
MANAGED_TABLES: frozenset[str] = (
    TENANT_TABLES
    | frozenset(EXTRA_COLUMNS)
    | frozenset(WIDEN_UNIQUE)
    | frozenset(ADD_UNIQUE)
    | frozenset(RELAX_UNIQUE)
    | frozenset(DROP_UNIQUE_BY_NAME)
    | frozenset(DROP_INDEX)
    | frozenset(ADD_INDEX)
)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _tenant_column() -> Column:
    return Column(
        TENANT_COLUMN,
        String(255),
        ForeignKey(TENANT_FK),
        nullable=False,
        index=True,
    )


def _has_index(table: Table, column_names: list[str]) -> bool:
    wanted = list(column_names)
    return any([c.name for c in ix.columns] == wanted for ix in table.indexes)


def _ensure_index(table: Table, column_name: str) -> None:
    """Ensure a NON-unique index exists on the column.

    Upstream may declare ``index=True, unique=True``, which builds an Index whose
    own ``unique`` flag is True. Clearing ``Column.unique`` does not change that
    Index, so the uniqueness survives as a unique index - and two tenants could
    not share a value. Relax any existing index as well as creating a missing one.
    """
    if column_name not in table.c:
        return
    for index in table.indexes:
        if [c.name for c in index.columns] == [column_name]:
            index.unique = False
            return
    Index(f"ix_{table.name}_{column_name}", table.c[column_name])


def _drop_unique(table: Table, column_names: list[str]) -> bool:
    """Remove a UniqueConstraint matching exactly these columns."""
    removed = False
    for constraint in list(table.constraints):
        if not isinstance(constraint, UniqueConstraint):
            continue
        if [c.name for c in constraint.columns] == column_names:
            table.constraints.discard(constraint)
            removed = True
    return removed


def _drop_named_unique(table: Table, name: str) -> UniqueConstraint | None:
    for constraint in list(table.constraints):
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            table.constraints.discard(constraint)
            return constraint
    return None


def _add_unique(table: Table, name: str, column_names: list[str]) -> None:
    if any(
        isinstance(c, UniqueConstraint) and c.name == name for c in table.constraints
    ):
        return
    missing = [c for c in column_names if c not in table.c]
    if missing:
        # Not an error: Alembic builds partial Table objects for operations like
        # op.create_index(), containing only the columns that operation needs.
        # Those are throwaway and must be left alone.
        LOGGER.debug(
            "tenant_schema: skipping %s on %s; columns %s absent (partial table)",
            name, table.name, missing,
        )
        return
    table.append_constraint(UniqueConstraint(*column_names, name=name))


# ---------------------------------------------------------------------------
# The listener
# ---------------------------------------------------------------------------


def apply_to_table(table: Table) -> None:
    """Apply m8flow's schema delta to one upstream table.

    Idempotent: safe to call twice on the same Table.
    """
    name = table.name
    if name not in MANAGED_TABLES:
        return

    # Alembic constructs partial, throwaway Table objects while running migration
    # operations - op.create_index() for instance builds one holding only the
    # indexed column. Applying m8flow's delta to those is wrong and, before this
    # guard, crashed the migration. Real mapped tables always declare a primary
    # key; Alembic's stubs do not.
    if not list(table.primary_key.columns):
        LOGGER.debug("tenant_schema: skipping %s (no primary key - partial table)", name)
        return

    # 1. tenant column
    if name in TENANT_TABLES and TENANT_COLUMN not in table.c:
        table.append_column(_tenant_column())

    # 2. m8flow-only columns
    for factory in EXTRA_COLUMNS.get(name, []):
        column = factory()
        if column.name not in table.c:
            table.append_column(column)

    # 3. relax upstream's global UNIQUE into per-tenant uniqueness
    for column_name in RELAX_UNIQUE.get(name, []):
        if column_name in table.c:
            table.c[column_name].unique = False
        _drop_unique(table, [column_name])
        _ensure_index(table, column_name)

    # 4. widen an existing composite UNIQUE to include the tenant column
    if name in WIDEN_UNIQUE:
        constraint_name, upstream_columns = WIDEN_UNIQUE[name]
        existing = _drop_named_unique(table, constraint_name)
        if existing is None:
            _drop_unique(table, upstream_columns)
        _add_unique(table, constraint_name, [TENANT_COLUMN, *upstream_columns])

    # 5a. upstream constraints m8flow replaces
    for constraint_name in DROP_UNIQUE_BY_NAME.get(name, []):
        _drop_named_unique(table, constraint_name)

    # 5b. constraints m8flow adds outright
    for constraint_name, column_names in ADD_UNIQUE.get(name, []):
        _add_unique(table, constraint_name, column_names)

    # 6. indexes m8flow drops
    for column_name in DROP_INDEX.get(name, []):
        for index in list(table.indexes):
            if [c.name for c in index.columns] == [column_name]:
                table.indexes.discard(index)

    # 7. indexes m8flow adds
    for column_name in ADD_INDEX.get(name, []):
        _ensure_index(table, column_name)


_REGISTERED = False


def register() -> None:
    """Install the listener. Must run before any model module is imported."""
    global _REGISTERED
    if _REGISTERED:
        return

    @event.listens_for(Table, "after_parent_attach")
    def _on_table_attached(table: Table, parent: object) -> None:  # noqa: ARG001
        # Never raise from here. This fires for every Table SQLAlchemy or Alembic
        # constructs, including internal ones we have no business touching, and an
        # exception aborts whatever created the table - a migration, or app boot.
        try:
            apply_to_table(table)
        except Exception:
            LOGGER.exception(
                "tenant_schema: failed applying delta to %s - continuing", table.name
            )

    _REGISTERED = True
    LOGGER.info("tenant_schema: listener registered for %d tables", len(MANAGED_TABLES))


def assert_applied(metadata: object) -> None:
    """Fail loudly if the listener registered too late to catch a table.

    A missing tenant column would otherwise surface as a NOT NULL violation on
    the first insert, in production, far from the cause.
    """
    tables = getattr(metadata, "tables", {})
    missing_tenant = [
        name
        for name in sorted(TENANT_TABLES)
        if name in tables and TENANT_COLUMN not in tables[name].c
    ]
    missing_extra = [
        f"{name}.{factory().name}"
        for name, factories in EXTRA_COLUMNS.items()
        if name in tables
        for factory in factories
        if factory().name not in tables[name].c
    ]
    if missing_tenant or missing_extra:
        raise RuntimeError(
            "tenant_schema was registered too late - these tables were built "
            f"without m8flow's columns. tenant: {missing_tenant}; extra: {missing_extra}. "
            "Call tenant_schema.register() before importing any model."
        )
