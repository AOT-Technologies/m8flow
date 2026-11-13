"""Bootstrap the complete M8Flow schema from an empty database.

This squashes the former incremental chain into a single root revision.

The old chain started by creating only ``m8flow_tenant`` and then, from the
very next revision, assumed the ~30 SpiffWorkflow-derived core tables already
existed (they were expected to have been created out-of-band by the retired
``spiffworkflow-backend`` migrations, which were never part of this repo). On a
genuinely fresh database ``alembic upgrade head`` therefore died with
``NoSuchTableError`` and the backend container crash-looped. See
``docs/upstream-recovery.md``.

This revision builds the base schema from the live ORM metadata
(``m8flow_backend.db.alembic_target_metadata()`` -> CoreBase + HostBase),
projecting out configuration-variable tables/columns/indexes owned by their
later additive revision. It then applies the pieces ``create_all`` cannot express:

* PostgreSQL row-level-security policies on every tenant-scoped table,
* the host-only ``uq_user_username_realm`` uniqueness constraint on ``user``
  (the core ORM does not model it), and
* the base ``m8flow`` tenant seed row.

The ``tenantstatus`` / ``tenantinvitationstatus`` enums are declared as
SQLAlchemy ``Enum`` columns, so ``create_all`` creates them automatically.

The installed ``m8flow-bpmn-core`` wheel does not package its Alembic scripts,
so a host deployment cannot execute the core migration chain separately.  The
schema created here is nevertheless already the schema represented by the
installed core head.  We therefore create the core Alembic marker alongside
that schema on a genuinely fresh database.  Existing databases keep their
marker untouched; the later breaking migration validates a non-empty marker
and completes the final core handoff when the marker is absent.

NOTE (squash): a database previously stamped at an old head revision
(e.g. ``v6g7h8i9j0k1``) cannot upgrade through this root - Alembic will not find
the old revision id. Fresh databases (the supported path) upgrade in one step.
For an existing, fully-migrated database, ``alembic stamp head`` after
confirming its schema already matches the ORM.

Revision ID: 1518b05122bc
Revises: (none - root)
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa

from m8flow_backend.db import combined_model_metadata

# revision identifiers, used by Alembic.
revision = "1518b05122bc"
down_revision = None
branch_labels = None
depends_on = None

USER_TABLE = "user"
USER_USERNAME_REALM_UNIQUE = "uq_user_username_realm"
CORE_VERSION_TABLE = "m8flow_core_alembic_version"
CORE_HEAD = "k2l3m4n5o6p7"

# Freeze the root revision's table scope. This revision is historical: using
# every table in today's ORM metadata during downgrade could drop a table added
# by a later model change. The configuration-variable tables belong to d2f4a6b8c0e1.
BASELINE_TABLE_NAMES = frozenset(
    {
        "api_log",
        "bpmn_process",
        "bpmn_process_definition",
        "configuration",
        "future_task",
        "json_data",
        "m8f_group",
        "m8flow_celery_task",
        "m8flow_connector_configuration",
        "m8flow_external_form_requests",
        "m8flow_nats_api_keys",
        "m8flow_nats_event_audit",
        "m8flow_process_instance_error",
        "m8flow_process_model_template",
        "m8flow_templates",
        "m8flow_tenant",
        "m8flow_tenant_invitation",
        "m8flow_tenant_permission_seed",
        "permission_assignment",
        "permission_target",
        "pkce_code_verifier",
        "principal",
        "process_instance",
        "process_instance_event",
        "process_instance_file_data",
        "process_instance_metadata",
        "process_model_bpmn_version",
        "refresh_token",
        "scheduler_job",
        "secret",
        "service_account",
        "task",
        "task_definition",
        "task_draft_data",
        "task_instructions_for_end_user",
        "typeahead",
        "user",
        "user_group_assignment",
        "work_item",
        "work_item_user",
    }
)

# Base tenant seed (matches the retired d2b8f0d1a4c5 seed revision).
BASE_TENANT_ID = "m8flow"
BASE_TENANT_SLUG = "m8flow"
BASE_TENANT_NAME = "M8Flow Realm"

_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _validate_baseline_tables(metadata: sa.MetaData) -> None:
    missing = sorted(BASELINE_TABLE_NAMES - set(metadata.tables))
    if missing:
        missing_names = ", ".join(missing)
        raise RuntimeError(
            "The 1518b05122bc migration baseline does not match the current ORM "
            f"metadata; expected baseline table(s) are missing: {missing_names}. "
            "Update BASELINE_TABLE_NAMES only after verifying the historical schema."
        )


def _create_all_tables() -> None:
    bind = op.get_bind()
    current_metadata = combined_model_metadata()
    _validate_baseline_tables(current_metadata)
    baseline = sa.MetaData()

    # This root migration is the historical schema baseline. The connector
    # variable revision below the current-main head owns these additions, so
    # do not create them here from today's ORM metadata or that later revision
    # would see a partially-applied schema and refuse to run.
    later_tables = {"m8flow_named_value", "m8flow_connector_variable"}
    later_connector_columns = {"provider_key", "schema_version"}
    for table in current_metadata.tables.values():
        if table.name in later_tables:
            continue
        copied = table.to_metadata(baseline)
        if table.name == "m8flow_connector_configuration":
            # These columns have no constraints or indexes in the ORM; remove
            # them from the copy so the later additive revision owns them.
            for column_name in later_connector_columns:
                column = copied.c.get(column_name)
                if column is not None:
                    copied._columns.remove(column)
            # The additive migration creates this index for the composite
            # connector-variable foreign key.
            for index in tuple(copied.indexes):
                if index.name == "uq_host_m8flow_connector_configuration_id_tenant":
                    copied.indexes.remove(index)

    baseline.create_all(bind, checkfirst=True)


def _quote_identifier(identifier: str) -> str:
    """Quote a schema identifier before embedding it in PostgreSQL DDL."""
    return op.get_bind().dialect.identifier_preparer.quote(identifier)


def _tenant_scoped_tables() -> list[str]:
    """Every table carrying an ``m8f_tenant_id`` column, resolved from the
    live schema so it always tracks whatever ``create_all`` just built."""
    if _is_postgres():
        rows = op.get_bind().execute(
            sa.text(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND column_name = 'm8f_tenant_id'
                ORDER BY table_name
                """
            )
        ).fetchall()
        return [str(row[0]) for row in rows]

    inspector = sa.inspect(op.get_bind())
    return [
        table
        for table in inspector.get_table_names()
        if any(column["name"] == "m8f_tenant_id" for column in inspector.get_columns(table))
    ]


def _enable_rls() -> None:
    """Apply the tenant-isolation + SELECT-only super-admin bypass policy pair.

    RLS is a PostgreSQL feature; on other dialects (the unit-test SQLite
    engine) this is a no-op, matching the retired a750/i2b3/s3d4 revisions.
    """
    if not _is_postgres():
        return

    for table in _tenant_scoped_tables():
        tenant_policy = f"{table}_tenant_isolation"
        bypass_policy = f"{table}_super_admin_select"
        quoted_table = _quote_identifier(table)
        quoted_tenant_policy = _quote_identifier(tenant_policy)
        quoted_bypass_policy = _quote_identifier(bypass_policy)

        op.execute(sa.DDL(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY"))

        op.execute(sa.DDL(f"DROP POLICY IF EXISTS {quoted_tenant_policy} ON {quoted_table}"))
        op.execute(
            sa.DDL(
                f"CREATE POLICY {quoted_tenant_policy} ON {quoted_table} "
                f"FOR ALL USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
            )
        )

        # Super-admin cross-tenant read is SELECT-only.
        op.execute(sa.DDL(f"DROP POLICY IF EXISTS {quoted_bypass_policy} ON {quoted_table}"))
        op.execute(
            sa.DDL(
                f"CREATE POLICY {quoted_bypass_policy} ON {quoted_table} "
                f"FOR SELECT USING {_BYPASS_PREDICATE}"
            )
        )


def _add_user_username_realm_unique() -> None:
    """UNIQUE(username, service) - a host constraint the core ORM omits.

    Emitted as ``ALTER TABLE ... ADD CONSTRAINT``, which SQLite cannot do, so
    this is PostgreSQL-only (the primary database). The unit-test SQLite engine
    builds ``user`` from the ORM, which never carried this constraint anyway.
    """
    if not _is_postgres():
        return
    inspector = sa.inspect(op.get_bind())
    existing = {constraint.get("name") for constraint in inspector.get_unique_constraints(USER_TABLE)}
    if USER_USERNAME_REALM_UNIQUE not in existing:
        op.create_unique_constraint(
            USER_USERNAME_REALM_UNIQUE, USER_TABLE, ["username", "service"]
        )


def _seed_base_tenant() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM m8flow_tenant WHERE id = :tenant_id"),
        {"tenant_id": BASE_TENANT_ID},
    ).scalar()
    if exists is not None:
        return

    now = datetime.now(UTC)
    bind.execute(
        sa.text(
            """
            INSERT INTO m8flow_tenant (
                id, name, slug, status, created_by, modified_by,
                created_at, updated_at
            )
            VALUES (
                :tenant_id, :tenant_name, :tenant_slug, 'ACTIVE', 'system', 'system',
                :now, :now
            )
            """
        ),
        {
            "tenant_id": BASE_TENANT_ID,
            "tenant_name": BASE_TENANT_NAME,
            "tenant_slug": BASE_TENANT_SLUG,
            "now": now,
        },
    )


def _bootstrap_core_version_marker() -> None:
    """Record the core head represented by the freshly created ORM schema.

    Core migrations are intentionally not shipped in the Python wheel.  On an
    empty database, ``create_all`` above creates the installed core version's
    final schema, so creating a dedicated core marker here makes the host
    migration chain self-contained without sharing Alembic's host bookkeeping
    table. Never overwrite an existing marker: the breaking host migration
    either validates it or completes the final core handoff explicitly.
    """
    bind = op.get_bind()
    if sa.inspect(bind).has_table(CORE_VERSION_TABLE):
        return
    op.create_table(
        CORE_VERSION_TABLE,
        sa.Column("version_num", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("version_num"),
    )
    core_version = sa.table(
        CORE_VERSION_TABLE,
        sa.column("version_num", sa.String(length=32)),
    )
    bind.execute(sa.insert(core_version).values(version_num=CORE_HEAD))


def upgrade() -> None:
    _create_all_tables()
    _bootstrap_core_version_marker()
    _add_user_username_realm_unique()
    _enable_rls()
    _seed_base_tenant()


def downgrade() -> None:
    bind = op.get_bind()
    current_metadata = combined_model_metadata()
    _validate_baseline_tables(current_metadata)
    if sa.inspect(bind).has_table(CORE_VERSION_TABLE):
        op.drop_table(CORE_VERSION_TABLE)
    # Keep the root revision's historical table scope even as the live ORM
    # metadata grows. Copying only these tables retains dependency ordering
    # without allowing a later model to expand the downgrade's destructive set.
    baseline = sa.MetaData()
    for table_name in sorted(BASELINE_TABLE_NAMES):
        table = current_metadata.tables.get(table_name)
        if table is not None:
            table.to_metadata(baseline)
    baseline.drop_all(bind, checkfirst=True)
