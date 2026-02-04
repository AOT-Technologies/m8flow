"""Unify tenant/template timestamp seconds migration and defaults.

Revision ID: 9f2d0e4c8abc
Revises: 22aaaa61d8f6
Create Date: 2026-02-04
"""

from __future__ import annotations

import time

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f2d0e4c8abc"
down_revision = "22aaaa61d8f6"
branch_labels = None
depends_on = None


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _backfill_seconds_columns(table: str, created_col: str, modified_col: str) -> None:
    """Backfill *_at_in_seconds from existing datetime columns.

    - For NULL modified timestamps (possible on templates), fall back to created timestamp.
    - For any remaining NULLs, fall back to current time.
    """
    dialect = _dialect_name()
    if dialect != "postgresql":
        raise RuntimeError(f"This migration is Postgres-only; got dialect {dialect!r}.")

    now_seconds = int(round(time.time()))
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET
              created_at_in_seconds = COALESCE(EXTRACT(EPOCH FROM {created_col})::int, :now_seconds),
              updated_at_in_seconds = COALESCE(EXTRACT(EPOCH FROM {modified_col})::int,
                                              EXTRACT(EPOCH FROM {created_col})::int,
                                              :now_seconds)
            WHERE created_at_in_seconds IS NULL OR updated_at_in_seconds IS NULL
            """
        ).bindparams(now_seconds=now_seconds)
    )


def upgrade() -> None:
    # Add seconds columns (nullable for backfill).
    with op.batch_alter_table("m8flow_tenant") as batch_op:
        batch_op.add_column(sa.Column("created_at_in_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("updated_at_in_seconds", sa.Integer(), nullable=True))

    with op.batch_alter_table("m8flow_templates") as batch_op:
        batch_op.add_column(sa.Column("created_at_in_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("updated_at_in_seconds", sa.Integer(), nullable=True))

    # Backfill from existing datetime columns.
    _backfill_seconds_columns("m8flow_tenant", created_col="created_at", modified_col="modified_at")
    _backfill_seconds_columns("m8flow_templates", created_col="created_at", modified_col="modified_at")

    # Enforce NOT NULL after backfill.
    with op.batch_alter_table("m8flow_tenant") as batch_op:
        batch_op.alter_column("created_at_in_seconds", nullable=False)
        batch_op.alter_column("updated_at_in_seconds", nullable=False)

    with op.batch_alter_table("m8flow_templates") as batch_op:
        batch_op.alter_column("created_at_in_seconds", nullable=False)
        batch_op.alter_column("updated_at_in_seconds", nullable=False)

    # Drop old datetime columns to prevent divergence.
    with op.batch_alter_table("m8flow_tenant") as batch_op:
        batch_op.drop_column("modified_at")
        batch_op.drop_column("created_at")

    with op.batch_alter_table("m8flow_templates") as batch_op:
        batch_op.drop_column("modified_at")
        batch_op.drop_column("created_at")

    # Postgres-only hardening for template seconds columns:
    # - ensure no remaining NULLs using NOW()
    # - add server-side defaults so future inserts never get NULLs
    op.execute(
        sa.text(
            """
            UPDATE m8flow_templates
            SET
              created_at_in_seconds = COALESCE(
                created_at_in_seconds,
                CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER)
              ),
              updated_at_in_seconds = COALESCE(
                updated_at_in_seconds,
                created_at_in_seconds,
                CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER)
              )
            WHERE created_at_in_seconds IS NULL
               OR updated_at_in_seconds IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE m8flow_templates
              ALTER COLUMN created_at_in_seconds
                SET DEFAULT CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER),
              ALTER COLUMN updated_at_in_seconds
                SET DEFAULT CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER)
            """
        )
    )


def downgrade() -> None:
    dialect = _dialect_name()
    if dialect != "postgresql":
        raise RuntimeError(f"This migration is Postgres-only; got dialect {dialect!r}.")

    # Drop the server defaults; leave the backfilled values as-is.
    op.execute(
        sa.text(
            """
            ALTER TABLE m8flow_templates
              ALTER COLUMN created_at_in_seconds DROP DEFAULT,
              ALTER COLUMN updated_at_in_seconds DROP DEFAULT
            """
        )
    )

    # Re-add datetime columns (best-effort; values are not fully recoverable).
    with op.batch_alter_table("m8flow_tenant") as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("m8flow_templates") as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill datetime columns from seconds.
    op.execute(
        sa.text(
            """
            UPDATE m8flow_tenant
            SET created_at = to_timestamp(created_at_in_seconds),
                modified_at = to_timestamp(updated_at_in_seconds)
            WHERE created_at IS NULL OR modified_at IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE m8flow_templates
            SET created_at = to_timestamp(created_at_in_seconds),
                modified_at = to_timestamp(updated_at_in_seconds)
            WHERE created_at IS NULL OR modified_at IS NULL
            """
        )
    )

    # Drop seconds columns.
    with op.batch_alter_table("m8flow_tenant") as batch_op:
        batch_op.drop_column("updated_at_in_seconds")
        batch_op.drop_column("created_at_in_seconds")

    with op.batch_alter_table("m8flow_templates") as batch_op:
        batch_op.drop_column("updated_at_in_seconds")
        batch_op.drop_column("created_at_in_seconds")
