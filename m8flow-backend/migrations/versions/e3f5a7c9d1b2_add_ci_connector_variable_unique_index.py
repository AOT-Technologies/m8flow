"""Enforce case-insensitive connector field uniqueness per profile.

Revision ID: e3f5a7c9d1b2
Revises: d2f4a6b8c0e1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "e3f5a7c9d1b2"
down_revision = "d2f4a6b8c0e1"
branch_labels = None
depends_on = None

TABLE_NAME = "m8flow_connector_variable"
INDEX_NAME = "uq_m8flow_connector_variable_field_ci"


def _index_exists(bind: sa.Connection) -> bool:
    if bind.dialect.name == "sqlite":
        return (
            bind.execute(
                sa.text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'index' AND name = :index_name"
                ),
                {"index_name": INDEX_NAME},
            ).first()
            is not None
        )
    return INDEX_NAME in {
        index["name"] for index in sa.inspect(bind).get_indexes(TABLE_NAME)
    }


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE_NAME not in sa.inspect(bind).get_table_names():
        raise RuntimeError(
            f"Cannot add {INDEX_NAME}: table {TABLE_NAME} does not exist."
        )
    if _index_exists(bind):
        return

    table = sa.Table(TABLE_NAME, sa.MetaData(), autoload_with=bind)
    duplicates = bind.execute(
        sa.select(
            table.c.connector_configuration_id,
            sa.func.lower(table.c.field_name).label("normalized_field_name"),
            sa.func.count().label("duplicate_count"),
        )
        .group_by(table.c.connector_configuration_id, sa.func.lower(table.c.field_name))
        .having(sa.func.count() > 1)
    ).all()
    if duplicates:
        profiles = ", ".join(
            f"{row.connector_configuration_id}:{row.normalized_field_name!r}"
            for row in duplicates[:20]
        )
        raise RuntimeError(
            "Cannot enforce case-insensitive connector field uniqueness because "
            f"duplicate fields already exist (profile:field): {profiles}. "
            "Rename or remove the duplicate fields before upgrading."
        )

    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["connector_configuration_id", sa.text("lower(field_name)")],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE_NAME not in sa.inspect(bind).get_table_names():
        return
    if _index_exists(bind):
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
