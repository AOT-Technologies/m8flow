"""Unify tenant/template timestamp seconds migration and defaults.

Revision ID: 9f2d0e4c8abc
Revises: 22aaaa61d8f6
Create Date: 2026-02-04
"""

from __future__ import annotations

import datetime as dt

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f2d0e4c8abc"
down_revision = "22aaaa61d8f6"
branch_labels = None
depends_on = None


def _utc_now() -> dt.datetime:
    """Use naive UTC to avoid timezone surprises across dialects."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _to_epoch_seconds(value: dt.datetime | None) -> int:
    if value is None:
        value = _utc_now()

    # If the DB returns timezone-aware datetimes, normalize to UTC.
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)

    return int(value.timestamp())


def _backfill_seconds_columns(
    table: str,
    id_col: str,
    created_col: str,
    modified_col: str,
    created_seconds_col: str,
    updated_seconds_col: str,
    batch_size: int = 5000,
) -> None:
    """Backfill seconds columns from datetime columns in a DB-agnostic way."""
    bind = op.get_bind()
    last_id = None

    while True:
        if last_id is None:
            rows = bind.execute(
                sa.text(
                    f"""
                    SELECT {id_col} AS id, {created_col} AS created_at, {modified_col} AS modified_at
                    FROM {table}
                    WHERE {created_seconds_col} IS NULL OR {updated_seconds_col} IS NULL
                    ORDER BY {id_col}
                    LIMIT :limit
                    """
                ),
                {"limit": batch_size},
            ).fetchall()
        else:
            rows = bind.execute(
                sa.text(
                    f"""
                    SELECT {id_col} AS id, {created_col} AS created_at, {modified_col} AS modified_at
                    FROM {table}
                    WHERE ({created_seconds_col} IS NULL OR {updated_seconds_col} IS NULL)
                      AND {id_col} > :last_id
                    ORDER BY {id_col}
                    LIMIT :limit
                    """
                ),
                {"last_id": last_id, "limit": batch_size},
            ).fetchall()

        if not rows:
            break

        for r in rows:
            created_dt = r.created_at
            modified_dt = r.modified_at if r.modified_at is not None else created_dt

            created_s = _to_epoch_seconds(created_dt)
            updated_s = _to_epoch_seconds(modified_dt)

            bind.execute(
                sa.text(
                    f"""
                    UPDATE {table}
                    SET {created_seconds_col} = COALESCE({created_seconds_col}, :created_s),
                        {updated_seconds_col} = COALESCE({updated_seconds_col}, :updated_s)
                    WHERE {id_col} = :id
                    """
                ),
                {"id": r.id, "created_s": created_s, "updated_s": updated_s},
            )

        last_id = rows[-1].id


def _backfill_datetime_columns(
    table: str,
    id_col: str,
    created_seconds_col: str,
    updated_seconds_col: str,
    created_col: str,
    modified_col: str,
    batch_size: int = 5000,
) -> None:
    """Backfill datetime columns from seconds columns in a DB-agnostic way (downgrade)."""
    bind = op.get_bind()
    last_id = None
    utc = dt.timezone.utc

    while True:
        if last_id is None:
            rows = bind.execute(
                sa.text(
                    f"""
                    SELECT {id_col} AS id, {created_seconds_col} AS created_s, {updated_seconds_col} AS updated_s
                    FROM {table}
                    ORDER BY {id_col}
                    LIMIT :limit
                    """
                ),
                {"limit": batch_size},
            ).fetchall()
        else:
            rows = bind.execute(
                sa.text(
                    f"""
                    SELECT {id_col} AS id, {created_seconds_col} AS created_s, {updated_seconds_col} AS updated_s
                    FROM {table}
                    WHERE {id_col} > :last_id
                    ORDER BY {id_col}
                    LIMIT :limit
                    """
                ),
                {"last_id": last_id, "limit": batch_size},
            ).fetchall()

        if not rows:
            break

        for r in rows:
            created_s = r.created_s if r.created_s is not None else int(dt.datetime.now(utc).timestamp())
            updated_s = r.updated_s if r.updated_s is not None else created_s
            created_at = dt.datetime.fromtimestamp(created_s, tz=utc)
            modified_at = dt.datetime.fromtimestamp(updated_s, tz=utc)

            bind.execute(
                sa.text(
                    f"""
                    UPDATE {table}
                    SET {created_col} = :created_at, {modified_col} = :modified_at
                    WHERE {id_col} = :id
                    """
                ),
                {"id": r.id, "created_at": created_at, "modified_at": modified_at},
            )

        last_id = rows[-1].id


def upgrade() -> None:
    # Add seconds columns (nullable for backfill).
    with op.batch_alter_table("m8flow_tenant") as batch_op:
        batch_op.add_column(sa.Column("created_at_in_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("updated_at_in_seconds", sa.Integer(), nullable=True))

    with op.batch_alter_table("m8flow_templates") as batch_op:
        batch_op.add_column(sa.Column("created_at_in_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("updated_at_in_seconds", sa.Integer(), nullable=True))

    # Backfill from existing datetime columns (portable).
    _backfill_seconds_columns(
        table="m8flow_tenant",
        id_col="id",
        created_col="created_at",
        modified_col="modified_at",
        created_seconds_col="created_at_in_seconds",
        updated_seconds_col="updated_at_in_seconds",
    )
    _backfill_seconds_columns(
        table="m8flow_templates",
        id_col="id",
        created_col="created_at",
        modified_col="modified_at",
        created_seconds_col="created_at_in_seconds",
        updated_seconds_col="updated_at_in_seconds",
    )

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


def downgrade() -> None:
    # Re-add datetime columns (nullable).
    with op.batch_alter_table("m8flow_tenant") as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("m8flow_templates") as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill datetime columns from seconds (portable).
    _backfill_datetime_columns(
        table="m8flow_tenant",
        id_col="id",
        created_seconds_col="created_at_in_seconds",
        updated_seconds_col="updated_at_in_seconds",
        created_col="created_at",
        modified_col="modified_at",
    )
    _backfill_datetime_columns(
        table="m8flow_templates",
        id_col="id",
        created_seconds_col="created_at_in_seconds",
        updated_seconds_col="updated_at_in_seconds",
        created_col="created_at",
        modified_col="modified_at",
    )

    # Drop seconds columns.
    with op.batch_alter_table("m8flow_tenant") as batch_op:
        batch_op.drop_column("updated_at_in_seconds")
        batch_op.drop_column("created_at_in_seconds")

    with op.batch_alter_table("m8flow_templates") as batch_op:
        batch_op.drop_column("updated_at_in_seconds")
        batch_op.drop_column("created_at_in_seconds")
