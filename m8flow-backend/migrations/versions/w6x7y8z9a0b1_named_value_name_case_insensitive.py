"""Enforce tenant-scoped case-insensitive named-value names.

Revision ID: w6x7y8z9a0b1
Revises: v5w6x7y8z9a0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "w6x7y8z9a0b1"
down_revision = "v5w6x7y8z9a0"
branch_labels = None
depends_on = None

TABLE = "m8flow_named_value"
OLD_CONSTRAINT = "uq_m8flow_named_value_tenant_name"
NEW_INDEX = "uq_m8flow_named_value_tenant_name_ci"


def _collision_message(bind: sa.Connection) -> str | None:
    collisions = bind.execute(
        sa.text(
            f"SELECT m8f_tenant_id, lower(name) AS normalized_name "
            f"FROM {TABLE} GROUP BY m8f_tenant_id, lower(name) "
            "HAVING count(*) > 1"
        )
    ).mappings()
    messages: list[str] = []
    for collision in collisions:
        names = bind.execute(
            sa.text(
                f"SELECT name FROM {TABLE} "
                "WHERE m8f_tenant_id = :tenant_id AND lower(name) = :name "
                "ORDER BY name"
            ),
            {"tenant_id": collision["m8f_tenant_id"], "name": collision["normalized_name"]},
        ).scalars()
        messages.append(
            f"tenant {collision['m8f_tenant_id']!r}: "
            + ", ".join(repr(name) for name in names)
        )
    if not messages:
        return None
    return (
        "Cannot enforce case-insensitive configuration-variable names because "
        "existing collisions must be resolved manually before rerunning the "
        "migration: "
        + "; ".join(messages)
    )


def _drop_existing_exact_name_uniqueness(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints(TABLE):
        columns = tuple(constraint.get("column_names") or ())
        if constraint.get("name") == OLD_CONSTRAINT or columns == ("m8f_tenant_id", "name"):
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table(TABLE, recreate="always") as batch:
                    batch.drop_constraint(constraint["name"])
            else:
                op.drop_constraint(constraint["name"], TABLE, type_="unique")
            break

    # Some deployments may have created the old rule as a standalone index.
    for index in sa.inspect(bind).get_indexes(TABLE):
        columns = tuple(index.get("column_names") or ())
        if index.get("unique") and (
            index.get("name") == OLD_CONSTRAINT or columns == ("m8f_tenant_id", "name")
        ):
            op.drop_index(index["name"], table_name=TABLE)


def upgrade() -> None:
    bind = op.get_bind()
    message = _collision_message(bind)
    if message:
        raise RuntimeError(message)

    _drop_existing_exact_name_uniqueness(bind)
    op.execute(
        sa.text(
            f"CREATE UNIQUE INDEX {NEW_INDEX} ON {TABLE} "
            "(m8f_tenant_id, lower(name))"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index(NEW_INDEX, table_name=TABLE)
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch:
            batch.create_unique_constraint(OLD_CONSTRAINT, ["m8f_tenant_id", "name"])
    else:
        op.create_unique_constraint(OLD_CONSTRAINT, TABLE, ["m8f_tenant_id", "name"])
