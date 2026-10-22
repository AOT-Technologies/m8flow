"""Backfill Task Review and Home task-count grants for existing tenants.

The canonical YAML seed is request-triggered for unmarked tenants. This
migration materializes the newly introduced role grants for existing tenants
before deployment is considered complete, and advances only already-marked
seed rows from v1 to v2. Unmarked tenants remain eligible for the full
canonical seed on their normal authentication path.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

LOGGER = logging.getLogger("alembic.runtime.migration")
_CURRENT_SEED_VERSION = 3
_ROLE_NAMES = ("tenant-admin", "reviewer", "submitter")
_TARGETS = (
    ("read", "/m8flow/task-review-access", "read"),
    ("read", "/m8flow/task-review-access/%", "read"),
    ("create", "/m8flow/task-review-access/%/submit", "create"),
    ("read", "/m8flow/home-task-count", "read"),
)


def _required_tables(bind) -> dict[str, sa.Table]:
    metadata = sa.MetaData()
    required = (
        "m8flow_tenant",
        "principal",
        "permission_target",
        "permission_assignment",
        "m8flow_tenant_permission_seed",
    )
    existing = set(sa.inspect(bind).get_table_names())
    missing = sorted(set(required) - existing)
    if missing:
        message = f"Cannot backfill tenant permissions; required tables are missing: {', '.join(missing)}"
        LOGGER.error(message)
        raise RuntimeError(message)
    group_table_name = next(
        (name for name in ("m8f_group", "group") if name in existing), None
    )
    if group_table_name is None:
        message = "Cannot backfill tenant permissions; group or m8f_group table is missing"
        LOGGER.error(message)
        raise RuntimeError(message)
    tables = {
        name: sa.Table(name, metadata, autoload_with=bind)
        for name in required
    }
    tables["group"] = sa.Table(group_table_name, metadata, autoload_with=bind)
    return tables


def _target_id(bind, target_table: sa.Table, *, command: str, resource_id: str) -> int:
    query = sa.select(target_table.c.id).where(
        target_table.c.command == command,
        target_table.c.resource_type == "tenant",
        target_table.c.resource_id == resource_id,
    )
    target_id = bind.execute(query).scalar_one_or_none()
    if target_id is not None:
        return target_id

    result = bind.execute(
        sa.insert(target_table).values(
            command=command,
            resource_type="tenant",
            resource_id=resource_id,
        )
    )
    return result.inserted_primary_key[0]


def _ensure_group_principal(bind, tables: dict[str, sa.Table], *, tenant_id: str, role: str) -> int:
    groups = tables["group"]
    principals = tables["principal"]
    identifier = f"{tenant_id}:{role}"
    authorization_key = f"authorization:{identifier}"
    group_id = bind.execute(
        sa.select(groups.c.id).where(
            groups.c.identifier == identifier,
            groups.c.authorization_key == authorization_key,
        )
    ).scalar_one_or_none()
    if group_id is None:
        result = bind.execute(
            sa.insert(groups).values(
                name=identifier,
                identifier=identifier,
                authorization_key=authorization_key,
            )
        )
        group_id = result.inserted_primary_key[0]

    principal_id = bind.execute(
        sa.select(principals.c.id).where(principals.c.group_id == group_id).limit(1)
    ).scalar_one_or_none()
    if principal_id is None:
        result = bind.execute(
            sa.insert(principals).values(user_id=None, group_id=group_id)
        )
        principal_id = result.inserted_primary_key[0]
    return principal_id


def _ensure_assignment(
    bind,
    assignments: sa.Table,
    *,
    principal_id: int,
    permission_target_id: int,
    permission: str,
) -> bool:
    existing = bind.execute(
        sa.select(assignments.c.id).where(
            assignments.c.principal_id == principal_id,
            assignments.c.permission_target_id == permission_target_id,
            assignments.c.permission == permission,
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Preserve any explicit operator deny or customized grant type.
        return False
    bind.execute(
        sa.insert(assignments).values(
            principal_id=principal_id,
            permission_target_id=permission_target_id,
            permission=permission,
            grant_type="permit",
        )
    )
    return True


def upgrade() -> None:
    bind = op.get_bind()
    tables = _required_tables(bind)
    target_table = tables["permission_target"]
    assignments = tables["permission_assignment"]
    targets = [
        (
            permission,
            resource_id,
            _target_id(
                bind,
                target_table,
                command=command,
                resource_id=resource_id,
            ),
        )
        for command, resource_id, permission in _TARGETS
    ]

    inserted_count = 0
    tenant_table = tables["m8flow_tenant"]
    marker_table = tables["m8flow_tenant_permission_seed"]
    tenant_ids = bind.execute(
        sa.select(tenant_table.c.id)
        .outerjoin(marker_table, marker_table.c.m8f_tenant_id == tenant_table.c.id)
        .where(
            sa.or_(
                marker_table.c.m8f_tenant_id.is_(None),
                marker_table.c.seed_version < _CURRENT_SEED_VERSION,
            )
        )
    ).scalars().all()
    for tenant_id in tenant_ids:
        for role in _ROLE_NAMES:
            principal_id = _ensure_group_principal(
                bind, tables, tenant_id=str(tenant_id), role=role
            )
            for permission, _resource_id, target_id in targets:
                inserted_count += _ensure_assignment(
                    bind,
                    assignments,
                    principal_id=principal_id,
                    permission_target_id=target_id,
                    permission=permission,
                )

    # Only tenants that already had a completed canonical seed can be
    # advanced. Leave unmarked tenants unmarked so request-time sync still
    # performs their complete initial YAML import.
    updated = bind.execute(
        sa.update(marker_table)
        .where(marker_table.c.seed_version < _CURRENT_SEED_VERSION)
        .values(seed_version=_CURRENT_SEED_VERSION)
    )
    LOGGER.info(
        "Backfilled %s Task Review/Home permission assignments; advanced %s tenant seed markers",
        inserted_count,
        updated.rowcount,
    )


def downgrade() -> None:
    # Keep the grants: later operator changes and new memberships may depend on
    # them, so a downgrade cannot safely distinguish these rows from edits.
    pass
