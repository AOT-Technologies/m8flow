"""Recognize historical migration names by purpose and verify their schema."""

from __future__ import annotations

import re
from uuid import uuid4

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_REVISION = re.compile(r"m8f_[0-9]+_(?P<purpose>[a-z_]+)")
_OWNERSHIP = re.compile(r"m8flow_m8f_[0-9]+_message_ownership")
_HOST_PURPOSES = {
    "core_message_schema": "core_message_schema",
    "merge_host_heads": "merge_message_host_heads",
    "merge_nats_permissions": "merge_message_nats_permissions",
    "merge_run_stats": "merge_message_run_stats",
}
MESSAGE_TABLES = (
    "signal_registry_state", "signal_publication", "signal_subscription", "signal_delivery",
    "message_subscription", "message_delivery_receipt",
)
OWNERSHIP_TABLE = "m8flow_message_schema_ownership"


def prepare_compensation_replay(connection: sa.Connection, migration_context, scripts) -> None:
    """Present the immutable journal revision with its historical FK shape.

    Only the upgrade step that actually replays that revision calls this.
    The later runtime revision restores the tenant-qualified references in
    the same outer transaction; failures roll back both schema and stamps.
    """
    historical = scripts.get_revision("fa8b9c0d1e2f").module
    message = scripts.get_revision("core_message_schema").module
    inspector = sa.inspect(connection)
    plans = []
    for name, items in historical._journal_definitions().items():
        if not inspector.has_table(name):
            continue
        keys = inspector.get_foreign_keys(name)
        composite = [key for key in keys if key["referred_table"] == "process_instance"
                     and set(key["constrained_columns"]) == {"m8f_tenant_id", "process_instance_id"}]
        if not composite:
            continue
        message._validate_journal_instance_keys(inspector, name)
        legacy = any(key["referred_table"] == "process_instance"
                     and key["constrained_columns"] == ["process_instance_id"] for key in keys)
        expected = sa.Table(name, sa.MetaData(), *items)
        if not legacy:
            for constraint in tuple(expected.foreign_key_constraints):
                if constraint.column_keys == ["process_instance_id"]:
                    expected.constraints.remove(constraint)
                    for element in constraint.elements:
                        expected.foreign_keys.discard(element)
                        element.parent.foreign_keys.discard(element)
        for key in composite:
            expected.append_constraint(sa.ForeignKeyConstraint(
                key["constrained_columns"], [f"process_instance.{column}" for column in key["referred_columns"]],
            ))
        historical._validate_existing_table(inspector, expected)
        plans.append((name, composite, legacy))
    if not plans:
        return
    # SQLite must start its write transaction before a batch table rebuild.
    connection.execute(sa.text("UPDATE alembic_version_m8flow SET version_num = version_num WHERE 1 = 0"))
    operations = Operations(migration_context)
    for name, composite, legacy in plans:
        naming = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
        with operations.batch_alter_table(name, naming_convention=naming) as batch:
            for key in composite:
                batch.drop_constraint(
                    key["name"] or f"fk_{name}_{key['constrained_columns'][0]}_process_instance",
                    type_="foreignkey",
                )
            if not legacy:
                batch.create_foreign_key(
                    f"fk_{name}_process_instance_id_process_instance", "process_instance", ["process_instance_id"], ["id"],
                )


def core_revision(value: str) -> str:
    """Return the canonical marker for the supported historical core schema."""
    match = _REVISION.fullmatch(value)
    if match and match["purpose"] == "message_correlation":
        return "message_correlation"
    if value.lower().startswith(("m8f_", "m8f-", "m8f ")) and (
        re.match(r"m8f[-_ ]+[0-9]", value, re.IGNORECASE) or value.lower().endswith("_message_correlation")
    ):
        raise RuntimeError(f"Unsupported historical core migration name: {value!r}")
    return value


def host_revision(value: str) -> str:
    """Keep unknown historical names out of the pre-squash bootstrap fallback."""
    match = _REVISION.fullmatch(value)
    if match and match["purpose"] in _HOST_PURPOSES:
        return _HOST_PURPOSES[match["purpose"]]
    if value.lower().startswith(("m8f_", "m8f-", "m8f ")):
        raise RuntimeError(f"Unsupported historical host migration name: {value!r}")
    return value


def require_message_schema(connection: sa.Connection) -> None:
    """Verify the message contract before changing historical bookkeeping."""
    from m8flow_core.models import Base

    inspector = sa.inspect(connection)
    implementation = MigrationContext.configure(connection).impl
    for name in MESSAGE_TABLES:
        expected = Base.metadata.tables[name]
        if not inspector.has_table(name):
            raise RuntimeError(f"Incompatible historical message schema: missing table {name}")
        columns = {column["name"]: column for column in inspector.get_columns(name)}
        for column in expected.columns:
            actual = columns.get(column.name)
            if actual is None or actual["nullable"] != column.nullable or implementation.compare_type(
                sa.Column(column.name, actual["type"]), column,
            ):
                raise RuntimeError(f"Incompatible historical message schema: {name}.{column.name}")
        primary_key = set(inspector.get_pk_constraint(name)["constrained_columns"])
        keys = {
            (tuple(key["constrained_columns"]), key["referred_table"], tuple(key["referred_columns"]))
            for key in inspector.get_foreign_keys(name)
            if key.get("referred_schema") in (None, inspector.default_schema_name)
        }
        expected_keys = {
            (tuple(key.column_keys), key.referred_table.name, tuple(element.column.name for element in key.elements))
            for key in expected.foreign_key_constraints
        }
        if not (set(expected.columns.keys()) <= columns.keys()
                and primary_key == set(expected.primary_key.columns.keys()) and expected_keys <= keys):
            raise RuntimeError(f"Incompatible historical message schema: {name}")
        checks = [key for key in expected.constraints if isinstance(key, sa.CheckConstraint)]
        if checks:
            # Reflect through the same dialect so PostgreSQL's rewritten casts
            # and IN expressions can be compared without weakening the checks.
            probe = sa.Table(
                f"message_schema_probe_{uuid4().hex}", sa.MetaData(),
                *(sa.Column(column.name, column.type) for column in expected.columns),
                *(sa.CheckConstraint(str(key.sqltext)) for key in checks), prefixes=["TEMPORARY"],
            )
            probe.create(connection)
            try:
                required = {key["sqltext"] for key in sa.inspect(connection).get_check_constraints(probe.name)}
            finally:
                probe.drop(connection)
            if not required <= {key["sqltext"] for key in inspector.get_check_constraints(name)}:
                raise RuntimeError(f"Incompatible historical message schema: {name} check constraints")


def compatible_core_revision(connection: sa.Connection, value: str) -> str:
    current = core_revision(value)
    if current != value:
        require_message_schema(connection)
    return current


def legacy_ownership_table(connection: sa.Connection) -> str | None:
    names = sa.inspect(connection).get_table_names()
    candidates = [name for name in names if name.lower().startswith("m8flow_m8f_") and name.lower().endswith("_message_ownership")]
    if any(not _OWNERSHIP.fullmatch(name) for name in candidates):
        raise RuntimeError("Malformed historical message ownership table name")
    if len(candidates) > 1 or (candidates and OWNERSHIP_TABLE in names):
        raise RuntimeError("Both legacy and current message ownership tables exist; reconcile provenance before upgrading.")
    if not candidates:
        return None
    name = candidates[0]
    inspector = sa.inspect(connection)
    if not {"table_name", "creation_marker"} <= {column["name"] for column in inspector.get_columns(name)}:
        raise RuntimeError("Incompatible historical message ownership table")
    if inspector.get_pk_constraint(name)["constrained_columns"] != ["table_name"]:
        raise RuntimeError("Incompatible historical message ownership primary key")
    table = sa.table(name, sa.column("table_name"), sa.column("creation_marker"))
    marker = connection.scalar(sa.select(table.c.creation_marker).where(table.c.table_name == name))
    if not marker or host_revision(marker) != "core_message_schema":
        raise RuntimeError("Missing or incompatible historical message ownership provenance")
    if marker != "core_message_schema" and name != f"m8flow_{marker.removesuffix('core_message_schema')}message_ownership":
        raise RuntimeError("Historical message ownership namespace does not match its provenance")
    require_message_schema(connection)
    return name
