"""Revoke tenant-wide process-instance read from submitter groups (M8F-534).

The permission seed is additive, so removing ``submitter`` from the YAML does not
remove grants already materialized in existing tenant databases. Delete only the
seeded read grants on ``/process-instances`` and ``/process-instances/%`` from
submitter groups; the narrower ``/process-instances/for-me`` grant arrives with
the next seed import. Downgrade restores the two deleted grants.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op


revision = "b9d2e3f4a5c6"
down_revision = "a8c1e2f3b4d5"
branch_labels = None
depends_on = None

LOGGER = logging.getLogger("alembic.runtime.migration")

_TENANT_WIDE_INSTANCE_TARGETS = ("/process-instances", "/process-instances/%")
# The (resource_id, command) targets the pre-M8F-534 YAML granted submitters `read` on.
_RESTORED_TARGETS = (
    ("/process-instances", "process_instance.list"),
    ("/process-instances/%", "process_instance.read"),
)


def _authorization_tables():
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
    return assignments, targets


def _group_table_name(bind) -> str:
    existing = set(sa.inspect(bind).get_table_names())
    for candidate in ("m8f_group", "group"):
        if candidate in existing:
            return candidate
    raise RuntimeError("Cannot locate the authorization group table")


def _submitter_principals_query(bind):
    metadata = sa.MetaData()
    principals = sa.Table("principal", metadata, autoload_with=bind)
    # Reflect the reserved-word table so the active dialect controls quoting.
    groups = sa.Table(_group_table_name(bind), metadata, autoload_with=bind)
    tenants = sa.Table("m8flow_tenant", metadata, autoload_with=bind)
    tenant_identifier = sa.cast(tenants.c.id, sa.String)
    tenant_submitter_identifiers = sa.select(tenant_identifier + sa.literal(":submitter"))
    return (
        sa.select(principals.c.id)
        .select_from(principals.join(groups, groups.c.id == principals.c.group_id))
        .where(
            sa.or_(
                # Legacy global submitter group, plus tenant-qualified groups whose
                # prefix is a real tenant ID. Other namespaced groups are untouched.
                groups.c.identifier == "submitter",
                groups.c.identifier.in_(tenant_submitter_identifiers),
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
            "Cannot revoke submitter tenant-wide instance grants; required authorization "
            f"tables are missing: {', '.join(missing)}"
        )
        LOGGER.error(message)
        raise RuntimeError(message)

    assignments, targets = _authorization_tables()
    instance_targets = sa.select(targets.c.id).where(
        targets.c.resource_type == "tenant",
        targets.c.resource_id.in_(_TENANT_WIDE_INSTANCE_TARGETS),
    )
    bind.execute(
        sa.delete(assignments).where(
            assignments.c.principal_id.in_(_submitter_principals_query(bind)),
            assignments.c.permission_target_id.in_(instance_targets),
            assignments.c.permission.in_(("read", "all")),
            assignments.c.grant_type == "permit",
        )
    )


def downgrade() -> None:
    # Code rolled back to before M8F-534 gates submitters' instance views on these
    # grants, and the tenant seed marker (already at 4) keeps it from re-importing
    # them, so put them back. Idempotent: skips principals that already hold one.
    bind = op.get_bind()
    assignments, targets = _authorization_tables()
    submitters = _submitter_principals_query(bind).subquery()
    for resource_id, command in _RESTORED_TARGETS:
        target_ids = bind.execute(
            sa.select(targets.c.id).where(
                targets.c.resource_type == "tenant",
                targets.c.resource_id == resource_id,
                targets.c.command == command,
            )
        ).scalars()
        for target_id in target_ids.all():
            # Any grant_type counts: the table is unique on (principal, target,
            # permission), so a deny row already holds the read slot, and upgrade
            # never deleted denies; leaving it is the pre-upgrade state.
            already_granted = sa.select(assignments.c.principal_id).where(
                assignments.c.permission_target_id == target_id,
                assignments.c.permission == "read",
            )
            bind.execute(
                sa.insert(assignments).from_select(
                    ["principal_id", "permission_target_id", "grant_type", "permission"],
                    sa.select(
                        submitters.c.id,
                        sa.literal(target_id),
                        sa.literal("permit"),
                        sa.literal("read"),
                    ).where(submitters.c.id.not_in(already_granted)),
                )
            )
