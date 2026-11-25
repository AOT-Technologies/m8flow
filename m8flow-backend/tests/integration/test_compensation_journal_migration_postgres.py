"""Exercise the compensation-journal FK preflight against PostgreSQL reflection."""

from __future__ import annotations

import runpy
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.usefixtures("migrated_database")

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "b6c7d8e9f0a1_scope_compensation_foreign_keys.py"
)


@pytest.mark.parametrize(
    ("key_kind", "column_order", "has_partial_key", "accepted"),
    [
        ("primary_key", ("m8f_tenant_id", "id"), False, True),
        ("unique_constraint", ("m8f_tenant_id", "id"), False, True),
        # PostgreSQL permits a referenced unique key in either column order;
        # the migration preflight should recognize the same semantic key.
        ("unique_index", ("id", "m8f_tenant_id"), False, True),
        ("unique_index", ("m8f_tenant_id", "id"), True, False),
        ("none", (), False, False),
    ],
)
def test_process_instance_fk_preflight_against_postgres(
    admin_engine, key_kind, column_order, has_partial_key, accepted
):
    """Validate PK/unique-key reflection using real PostgreSQL catalog metadata."""
    migration = runpy.run_path(str(MIGRATION))
    table_name = f"fk_preflight_{uuid.uuid4().hex[:12]}"
    metadata = sa.MetaData()
    constraints = []
    if key_kind == "primary_key":
        constraints.append(sa.PrimaryKeyConstraint(*column_order))
    elif key_kind == "unique_constraint":
        constraints.append(sa.UniqueConstraint(*column_order))

    table = sa.Table(
        table_name,
        metadata,
        sa.Column("m8f_tenant_id", sa.String(64), nullable=False),
        sa.Column("id", sa.BigInteger, nullable=False),
        *constraints,
    )
    created = False

    try:
        with admin_engine.begin() as connection:
            table.create(connection)
            created = True
            if key_kind == "unique_index":
                index_kwargs = {"unique": True}
                if has_partial_key:
                    index_kwargs["postgresql_where"] = table.c.m8f_tenant_id != ""
                index = sa.Index(
                    f"ix_{table_name}_tenant_id",
                    *(table.c[column] for column in column_order),
                    **index_kwargs,
                )
                index.create(connection)

            if accepted:
                migration["_validate_process_instance_tenant_key"](
                    connection, table_name=table_name
                )
            else:
                with pytest.raises(RuntimeError, match="covering exactly"):
                    migration["_validate_process_instance_tenant_key"](
                        connection, table_name=table_name
                    )
    finally:
        if created:
            with admin_engine.begin() as connection:
                sa.Table(table_name, sa.MetaData(), autoload_with=connection).drop(connection)
