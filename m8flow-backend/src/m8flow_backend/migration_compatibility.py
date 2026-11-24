"""Recognize historical migration names by purpose and verify their schema."""

from __future__ import annotations

import re

import sqlalchemy as sa

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
    """Require columns, primary keys, and tenant relationships before adoption."""
    from m8flow_core.models import Base

    inspector = sa.inspect(connection)
    for name in MESSAGE_TABLES:
        expected = Base.metadata.tables[name]
        if not inspector.has_table(name):
            raise RuntimeError(f"Incompatible historical message schema: missing table {name}")
        columns = {column["name"] for column in inspector.get_columns(name)}
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
        if not (set(expected.columns.keys()) <= columns
                and primary_key == set(expected.primary_key.columns.keys()) and expected_keys <= keys):
            raise RuntimeError(f"Incompatible historical message schema: {name}")


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
