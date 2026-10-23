"""Add m8flow_process_model_version (published process-model snapshots).

Saving a published model now changes only its working copy on disk; Start runs
the newest row here until Publish changes snapshots the working copy again.

Databases created by the root revision build from the live ORM metadata, so the
create is skipped when the table already exists (same guard as b7e1c2d3f4a5).
The PostgreSQL row-level-security policy pair is (re)applied either way.

Also backfills the publish / version-history / revert grants for existing
tenants. Those prefixes are grant-only (no editor/tenant-admin group
fallback), so without this a tenant seeded earlier would 403/404 on Publish,
History and Revert until its next request-time re-seed. Mirrors the Task
Review/Home backfill (b8c9d0e1f2a3) and reuses its helpers.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None

TABLE_NAME = "m8flow_process_model_version"

LOGGER = logging.getLogger("alembic.runtime.migration")
_CURRENT_SEED_VERSION = 4
# (command, resource_id, permission, roles): the rows the canonical YAML seed writes for
# read-/revert-process-model-versions and publish-process-models in config/permissions/m8flow.yml.
# super-admin is global and passes allow_uri's super-admin shortcut, so it needs no tenant row.
_GRANTS = (
    ("read", "/process-model-versions/%", "read", ("tenant-admin", "editor", "viewer")),
    ("update", "/process-model-versions/%", "update", ("tenant-admin", "editor")),
    ("create", "/process-model-publish/%", "create", ("tenant-admin", "editor")),
)

# Same names and predicates as the root revision's _enable_rls (1518b05122bc).
_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE_NAME)


def _enable_rls() -> None:
    """Tenant isolation + SELECT-only super-admin bypass. PostgreSQL only."""
    if op.get_bind().dialect.name != "postgresql":
        return
    preparer = op.get_bind().dialect.identifier_preparer
    table = preparer.quote(TABLE_NAME)
    tenant_policy = preparer.quote(f"{TABLE_NAME}_tenant_isolation")
    bypass_policy = preparer.quote(f"{TABLE_NAME}_super_admin_select")
    op.execute(sa.DDL(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {tenant_policy} ON {table}"))
    op.execute(
        sa.DDL(
            f"CREATE POLICY {tenant_policy} ON {table} "
            f"FOR ALL USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
        )
    )
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {bypass_policy} ON {table}"))
    op.execute(sa.DDL(f"CREATE POLICY {bypass_policy} ON {table} FOR SELECT USING {_BYPASS_PREDICATE}"))


def _create_table() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("m8f_tenant_id", sa.String(255), nullable=False),
        sa.Column("process_model_identifier", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("primary_file_name", sa.String(255), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("published_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name=f"pk_host_{TABLE_NAME}"),
        sa.UniqueConstraint(
            "m8f_tenant_id",
            "process_model_identifier",
            "version",
            name="uq_process_model_version_tenant",
        ),
    )
    for column in ("m8f_tenant_id", "process_model_identifier"):
        op.create_index(f"ix_host_{TABLE_NAME}_{column}", TABLE_NAME, [column])


def _require_created_at() -> None:
    """A table built from older metadata may allow NULL created_at: backfill, then forbid."""
    column = next(c for c in sa.inspect(op.get_bind()).get_columns(TABLE_NAME) if c["name"] == "created_at")
    if not column["nullable"]:
        return
    created_at = sa.column("created_at", sa.DateTime(timezone=True))
    op.execute(
        sa.table(TABLE_NAME, created_at).update().where(created_at.is_(None)).values(created_at=sa.func.now())
    )
    alter = {"existing_type": sa.DateTime(timezone=True), "nullable": False, "server_default": sa.func.now()}
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(TABLE_NAME, recreate="always") as batch:
            batch.alter_column("created_at", **alter)
    else:
        op.alter_column(TABLE_NAME, "created_at", **alter)


def _backfill_helpers():
    # Migration modules are frozen once released, so the Task Review backfill's helpers are safe to reuse.
    path = Path(__file__).with_name("b8c9d0e1f2a3_backfill_task_review_home_permissions.py")
    spec = importlib.util.spec_from_file_location("_m8flow_permission_backfill_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _backfill_publish_grants() -> None:
    helpers = _backfill_helpers()
    bind = op.get_bind()
    tables = helpers._required_tables(bind)
    marker_table = tables["m8flow_tenant_permission_seed"]
    tenant_table = tables["m8flow_tenant"]
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
    inserted_count = 0
    for command, resource_id, permission, roles in _GRANTS:
        target_id = helpers._target_id(bind, tables["permission_target"], command=command, resource_id=resource_id)
        for tenant_id in tenant_ids:
            for role in roles:
                principal_id = helpers._ensure_group_principal(bind, tables, tenant_id=str(tenant_id), role=role)
                # Keeps an existing row as is: an operator's deny (maker-checker) is not re-granted.
                inserted_count += helpers._ensure_assignment(
                    bind,
                    tables["permission_assignment"],
                    principal_id=principal_id,
                    permission_target_id=target_id,
                    permission=permission,
                )
    # Unmarked tenants stay unmarked so request-time sync still runs their complete initial seed.
    updated = bind.execute(
        sa.update(marker_table)
        .where(marker_table.c.seed_version < _CURRENT_SEED_VERSION)
        .values(seed_version=_CURRENT_SEED_VERSION)
    )
    LOGGER.info(
        "Backfilled %s process-model publish/version permission assignments; advanced %s tenant seed markers",
        inserted_count,
        updated.rowcount,
    )


def upgrade() -> None:
    if _table_exists():
        _require_created_at()
    else:
        _create_table()
    _enable_rls()
    _backfill_publish_grants()


def downgrade() -> None:
    if not _table_exists():
        return
    if op.get_bind().dialect.name == "postgresql":
        # Explicit, rather than relying on DROP TABLE cascading to its policies.
        preparer = op.get_bind().dialect.identifier_preparer
        table = preparer.quote(TABLE_NAME)
        for suffix in ("tenant_isolation", "super_admin_select"):
            op.execute(sa.DDL(f"DROP POLICY IF EXISTS {preparer.quote(f'{TABLE_NAME}_{suffix}')} ON {table}"))
    op.drop_table(TABLE_NAME)
