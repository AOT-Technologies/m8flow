"""Revoke NATS event-history read from tenant-admin groups (M8F-700).

The NATS monitor, event history included, is super-admin only again. The permission
seed is additive, so removing ``tenant-admin`` from the YAML does not remove grants
already materialized in existing tenant databases. Delete only the two seeded read
grants for the event-history endpoints from tenant-admin groups; super-admin keeps
them through ``/m8flow/nats/*``.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op


revision = "c7e9a1b3d5f7"
down_revision = "c81d2e3f4a56"
branch_labels = None
depends_on = None

LOGGER = logging.getLogger("alembic.runtime.migration")

# Stored form of the YAML URIs: the target model rewrites the `*` wildcard to `%`.
_EVENT_HISTORY_RESOURCE_IDS = ("/m8flow/nats/events", "/m8flow/nats/events/%")


def _group_table_name(bind) -> str:
    existing = set(sa.inspect(bind).get_table_names())
    for candidate in ("m8f_group", "group"):
        if candidate in existing:
            return candidate
    raise RuntimeError("Cannot locate the authorization group table")


def _tenant_admin_principals_query(bind):
    metadata = sa.MetaData()
    principals = sa.Table("principal", metadata, autoload_with=bind)
    # Reflect the reserved-word table so the active dialect controls quoting.
    groups = sa.Table(_group_table_name(bind), metadata, autoload_with=bind)
    tenants = sa.Table("m8flow_tenant", metadata, autoload_with=bind)
    tenant_identifier = sa.cast(tenants.c.id, sa.String)
    tenant_admin_identifiers = sa.select(tenant_identifier + sa.literal(":tenant-admin"))
    return (
        sa.select(principals.c.id)
        .select_from(principals.join(groups, groups.c.id == principals.c.group_id))
        .where(
            sa.or_(
                # Legacy global group, plus tenant-qualified groups whose prefix is a
                # real tenant ID. Arbitrary namespaced groups are left untouched.
                groups.c.identifier == "tenant-admin",
                groups.c.identifier.in_(tenant_admin_identifiers),
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
            "Cannot revoke tenant-admin NATS event-history grants; required authorization "
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
    event_history_targets = sa.select(targets.c.id).where(
        targets.c.command == "read",
        targets.c.resource_type == "tenant",
        targets.c.resource_id.in_(_EVENT_HISTORY_RESOURCE_IDS),
    )
    bind.execute(
        sa.delete(assignments).where(
            assignments.c.principal_id.in_(_tenant_admin_principals_query(bind)),
            assignments.c.permission_target_id.in_(event_history_targets),
            assignments.c.permission == "read",
            assignments.c.grant_type == "permit",
        )
    )


def downgrade() -> None:
    # Fails closed: do not restore a grant that operators may have intentionally removed.
    pass
