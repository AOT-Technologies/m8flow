"""Use UUID primary keys for connector configurations.

Existing configuration IDs are replaced with generated UUIDs and dependent
connector-variable rows are updated in the same transaction. The migration is
intentionally last in the connector schema chain so already-applied databases
can upgrade without losing profile rows or provider documents.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op


revision = "v5w6x7y8z9a0"
down_revision = "u4v5w6x7y8z9"
branch_labels = None
depends_on = None

CONFIGURATION_TABLE = "m8flow_connector_configuration"
VARIABLE_TABLE = "m8flow_connector_variable"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _replace_postgres_columns() -> None:
    """Replace the key columns after the temporary UUID values are filled."""
    # PostgreSQL cannot alter a primary-key column while the child FK and its
    # indexes still reference it. Drop only those dependent objects; all other
    # profile indexes, RLS policies, and row data remain in place.
    op.execute(
        sa.text(
            f"ALTER TABLE {VARIABLE_TABLE} "
            "DROP CONSTRAINT IF EXISTS "
            "m8flow_connector_variable_connector_configuration_id_fkey"
        )
    )
    op.execute(sa.text("DROP INDEX IF EXISTS ix_m8flow_connector_variable_connector_configuration_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_m8flow_connector_variable_tenant_configuration"))
    op.execute(sa.text(f"ALTER TABLE {VARIABLE_TABLE} DROP CONSTRAINT IF EXISTS uq_m8flow_connector_variable_field"))
    op.execute(sa.text(f"ALTER TABLE {CONFIGURATION_TABLE} DROP CONSTRAINT IF EXISTS {CONFIGURATION_TABLE}_pkey"))

    op.execute(sa.text(f"ALTER TABLE {CONFIGURATION_TABLE} DROP COLUMN id"))
    op.execute(sa.text(f"ALTER TABLE {CONFIGURATION_TABLE} RENAME COLUMN id_uuid TO id"))
    op.execute(sa.text(f"ALTER TABLE {CONFIGURATION_TABLE} ALTER COLUMN id SET NOT NULL"))
    op.execute(sa.text(f"ALTER TABLE {CONFIGURATION_TABLE} ADD CONSTRAINT {CONFIGURATION_TABLE}_pkey PRIMARY KEY (id)"))

    op.execute(sa.text(f"ALTER TABLE {VARIABLE_TABLE} DROP COLUMN connector_configuration_id"))
    op.execute(sa.text(f"ALTER TABLE {VARIABLE_TABLE} RENAME COLUMN connector_configuration_uuid TO connector_configuration_id"))
    op.execute(sa.text(f"ALTER TABLE {VARIABLE_TABLE} ALTER COLUMN connector_configuration_id SET NOT NULL"))
    op.execute(
        sa.text(
            f"ALTER TABLE {VARIABLE_TABLE} ADD CONSTRAINT "
            "fk_m8flow_connector_variable_configuration FOREIGN KEY "
            "(connector_configuration_id) REFERENCES "
            f"{CONFIGURATION_TABLE}(id) ON DELETE CASCADE"
        )
    )
    op.execute(
        sa.text(
            f"ALTER TABLE {VARIABLE_TABLE} ADD CONSTRAINT uq_m8flow_connector_variable_field "
            "UNIQUE (connector_configuration_id, field_name)"
        )
    )
    op.create_index(
        "ix_m8flow_connector_variable_connector_configuration_id",
        VARIABLE_TABLE,
        ["connector_configuration_id"],
    )
    op.create_index(
        "ix_m8flow_connector_variable_tenant_configuration",
        VARIABLE_TABLE,
        ["m8f_tenant_id", "connector_configuration_id"],
    )


def upgrade() -> None:
    bind = op.get_bind()
    config = sa.table(
        CONFIGURATION_TABLE,
        sa.column("id", sa.Integer()),
        sa.column("id_uuid", sa.String(36)),
    )
    variable = sa.table(
        VARIABLE_TABLE,
        sa.column("connector_configuration_id", sa.Integer()),
        sa.column("connector_configuration_uuid", sa.String(36)),
    )

    # Add temporary UUID columns and build a mapping before changing either FK.
    op.add_column(CONFIGURATION_TABLE, sa.Column("id_uuid", sa.String(36), nullable=True))
    rows = bind.execute(sa.select(config.c.id)).all()
    id_map = {row.id: str(uuid.uuid4()) for row in rows}
    for old_id, new_id in id_map.items():
        bind.execute(
            config.update().where(config.c.id == old_id).values(id_uuid=new_id)
        )

    op.add_column(
        VARIABLE_TABLE,
        sa.Column("connector_configuration_uuid", sa.String(36), nullable=True),
    )
    for old_id, new_id in id_map.items():
        bind.execute(
            variable.update()
            .where(variable.c.connector_configuration_id == old_id)
            .values(connector_configuration_uuid=new_id)
        )

    # PostgreSQL needs explicit dependency ordering because the existing PK,
    # FK, unique constraint, and child indexes all reference the integer key.
    # The sequence is no longer used after the integer column is removed.
    if _is_postgres():
        _replace_postgres_columns()
        op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {CONFIGURATION_TABLE}_id_seq"))
        return

    # SQLite has no ALTER COLUMN support, so batch mode recreates the tables.
    # Profile metadata and provider_key values are copied intact.
    with op.batch_alter_table(VARIABLE_TABLE, recreate="always") as batch:
        batch.drop_column("connector_configuration_id")
        batch.alter_column(
            "connector_configuration_uuid",
            new_column_name="connector_configuration_id",
            existing_type=sa.String(36),
            nullable=False,
        )

    with op.batch_alter_table(CONFIGURATION_TABLE, recreate="always") as batch:
        batch.drop_column("id")
        batch.alter_column(
            "id_uuid",
            new_column_name="id",
            existing_type=sa.String(36),
            nullable=False,
        )

    # Batch recreation does not infer a primary key from a renamed temporary
    # column, so add it explicitly for SQLite.
    inspector = sa.inspect(bind)
    config_pk = inspector.get_pk_constraint(CONFIGURATION_TABLE).get("constrained_columns") or []
    if config_pk != ["id"]:
        op.create_primary_key(f"pk_{CONFIGURATION_TABLE}", CONFIGURATION_TABLE, ["id"])


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading UUID connector configuration IDs is not supported automatically; "
        "restore a database backup to avoid changing immutable provider paths."
    )
