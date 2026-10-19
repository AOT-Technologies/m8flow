"""Revoke the Home task-count permission from editor groups.

The permission seed is additive, so removing ``editor`` from the YAML does not
remove grants already materialized in existing tenant databases. Delete only
the seeded read grant for this endpoint from tenant-scoped editor groups.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "f6a7b8c9d0e1"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _editor_principals_query():
    principals = sa.table("principal", sa.column("id"), sa.column("group_id"))
    # ``group`` is reserved in PostgreSQL; preserve explicit quoting when
    # building this lightweight table clause (unlike reflected Table objects,
    # ``sa.table`` does not infer reserved-word quoting).
    groups = sa.table(
        sa.sql.quoted_name("group", quote=True),
        sa.column("id"),
        sa.column("identifier"),
    )
    return (
        sa.select(principals.c.id)
        .select_from(principals.join(groups, groups.c.id == principals.c.group_id))
        .where(sa.or_(groups.c.identifier == "editor", groups.c.identifier.like("%:editor")))
    )


def upgrade() -> None:
    required = {"permission_assignment", "permission_target", "principal", "group"}
    if not all(_table_exists(name) for name in required):
        return

    assignments = sa.table(
        "permission_assignment",
        sa.column("principal_id"),
        sa.column("permission_target_id"),
        sa.column("grant_type"),
        sa.column("permission"),
    )
    targets = sa.table(
        "permission_target",
        sa.column("id"),
        sa.column("command"),
        sa.column("resource_type"),
        sa.column("resource_id"),
    )
    editor_principals = _editor_principals_query()
    task_count_targets = sa.select(targets.c.id).where(
        targets.c.command == "read",
        targets.c.resource_type == "tenant",
        targets.c.resource_id == "/m8flow/home-task-count",
    )
    op.get_bind().execute(
        sa.delete(assignments).where(
            assignments.c.principal_id.in_(editor_principals),
            assignments.c.permission_target_id.in_(task_count_targets),
            assignments.c.permission == "read",
            assignments.c.grant_type == "permit",
        )
    )


def downgrade() -> None:
    # Do not restore a grant that operators may have intentionally removed.
    pass
