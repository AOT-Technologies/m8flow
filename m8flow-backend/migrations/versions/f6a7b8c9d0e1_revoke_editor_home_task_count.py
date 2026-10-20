"""Revoke the Home task-count permission from editor groups.

The permission seed is additive, so removing ``editor`` from the YAML does not
remove grants already materialized in existing tenant databases. Delete only
the seeded read grant for this endpoint from tenant-scoped editor groups.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op


revision = "f6a7b8c9d0e1"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None

LOGGER = logging.getLogger("alembic.runtime.migration")


def _group_table_name(bind) -> str:
    existing = set(sa.inspect(bind).get_table_names())
    for candidate in ("m8f_group", "group"):
        if candidate in existing:
            return candidate
    raise RuntimeError("Cannot locate the authorization group table")


def _editor_principals_query(bind):
    metadata = sa.MetaData()
    principals = sa.Table("principal", metadata, autoload_with=bind)
    # Reflect the reserved-word table so the active dialect controls quoting.
    groups = sa.Table(_group_table_name(bind), metadata, autoload_with=bind)
    tenants = sa.Table("m8flow_tenant", metadata, autoload_with=bind)
    tenant_identifier = sa.cast(tenants.c.id, sa.String)
    tenant_editor_identifiers = sa.select(tenant_identifier + sa.literal(":editor"))
    return (
        sa.select(principals.c.id)
        .select_from(principals.join(groups, groups.c.id == principals.c.group_id))
        .where(
            sa.or_(
                # Retain support for the legacy global editor group, but only
                # recognize tenant-qualified groups whose prefix is a real
                # tenant ID. Arbitrary namespaced groups are left untouched.
                groups.c.identifier == "editor",
                groups.c.identifier.in_(tenant_editor_identifiers),
            )
        )
    )


def upgrade() -> None:
    required = {
        "permission_assignment",
        "permission_target",
        "principal",
        "m8flow_tenant",
    }
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    missing = sorted(required - existing)
    if not {"group", "m8f_group"}.intersection(existing):
        missing.append("group or m8f_group")
    if missing:
        message = (
            "Cannot revoke editor Home task-count grants; required authorization "
            f"tables are missing: {', '.join(missing)}"
        )
        LOGGER.error(message)
        raise RuntimeError(message)

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
    editor_principals = _editor_principals_query(bind)
    task_count_targets = sa.select(targets.c.id).where(
        targets.c.command == "read",
        targets.c.resource_type == "tenant",
        targets.c.resource_id == "/m8flow/home-task-count",
    )
    bind.execute(
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
