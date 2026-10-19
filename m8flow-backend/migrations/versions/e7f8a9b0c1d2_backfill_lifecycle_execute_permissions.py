"""Backfill execute grants for process lifecycle commands.

Older M8Flow permission seeds represented process lifecycle operations with the
``create`` permission.  Current authorization requests use the explicit
``execute`` permission for suspend, resume, retry, and terminate.  Copy the
legacy assignments to ``execute`` during upgrade so existing tenants do not
depend on request-time YAML reseeding to become usable.

The legacy rows are intentionally retained.  They are harmless to the new
authorization path, preserve downgrade/older-worker compatibility, and avoid
deleting manually managed grants during a data-only migration.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op


revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None

LOGGER = logging.getLogger("alembic.runtime.migration")
_LIFECYCLE_COMMANDS = (
    "process.suspend",
    "process.resume",
    "process.retry",
    "process.terminate",
)


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _table(name: str, *columns: str) -> sa.TableClause:
    return sa.table(name, *(sa.column(column) for column in columns))


def upgrade() -> None:
    if not all(_table_exists(name) for name in ("permission_assignment", "permission_target")):
        return

    assignments = _table(
        "permission_assignment",
        "principal_id",
        "permission_target_id",
        "grant_type",
        "permission",
    )
    targets = _table("permission_target", "id", "command")
    legacy = assignments.alias("legacy_assignment")
    current = assignments.alias("current_assignment")

    source = (
        sa.select(
            legacy.c.principal_id,
            legacy.c.permission_target_id,
            legacy.c.grant_type,
            sa.literal("execute").label("permission"),
        )
        .select_from(legacy.join(targets, targets.c.id == legacy.c.permission_target_id))
        .where(legacy.c.permission == "create")
        .where(targets.c.command.in_(_LIFECYCLE_COMMANDS))
        .where(
            ~sa.exists(
                sa.select(1)
                .select_from(current)
                .where(current.c.principal_id == legacy.c.principal_id)
                .where(current.c.permission_target_id == legacy.c.permission_target_id)
                .where(current.c.permission == "execute")
            )
        )
    )

    result = op.get_bind().execute(
        sa.insert(assignments).from_select(
            ["principal_id", "permission_target_id", "grant_type", "permission"],
            source,
        )
    )
    missing = op.get_bind().execute(
        sa.select(legacy.c.principal_id, legacy.c.permission_target_id)
        .select_from(legacy.join(targets, targets.c.id == legacy.c.permission_target_id))
        .where(legacy.c.permission == "create")
        .where(targets.c.command.in_(_LIFECYCLE_COMMANDS))
        .where(
            ~sa.exists(
                sa.select(1)
                .select_from(current)
                .where(current.c.principal_id == legacy.c.principal_id)
                .where(current.c.permission_target_id == legacy.c.permission_target_id)
                .where(current.c.permission == "execute")
            )
        )
        .limit(20)
    ).all()
    if missing:
        raise RuntimeError(
            "Lifecycle execute grant backfill is incomplete for assignments: "
            f"{missing}"
        )
    LOGGER.info("Backfilled %s lifecycle execute permission assignments", result.rowcount)


def downgrade() -> None:
    # The migration only adds missing assignments and deliberately retains the
    # legacy create rows. Removing execute rows here could delete grants that
    # were created independently after the upgrade.
    pass
