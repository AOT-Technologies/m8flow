"""Bootstrap the complete M8Flow schema from an empty database.

This squashes the former incremental chain into a single root revision.

The old chain started by creating only ``m8flow_tenant`` and then, from the
very next revision, assumed the ~30 SpiffWorkflow-derived core tables already
existed (they were expected to have been created out-of-band by the retired
``spiffworkflow-backend`` migrations, which were never part of this repo). On a
genuinely fresh database ``alembic upgrade head`` therefore died with
``NoSuchTableError`` and the backend container crash-looped. See
``docs/upstream-recovery.md``.

This revision builds every table from the live ORM metadata
(``m8flow_backend.db.alembic_target_metadata()`` -> CoreBase + HostBase), then
applies the pieces ``create_all`` cannot express:

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

from m8flow_backend.db import alembic_target_metadata

# revision identifiers, used by Alembic.
revision = "1518b05122bc"
down_revision = None
branch_labels = None
depends_on = None

USER_TABLE = "user"
USER_USERNAME_REALM_UNIQUE = "uq_user_username_realm"
CORE_VERSION_TABLE = "alembic_version"
CORE_HEAD = "k2l3m4n5o6p7"

# Base tenant seed (matches the retired d2b8f0d1a4c5 seed revision).
BASE_TENANT_ID = "m8flow"
BASE_TENANT_SLUG = "m8flow"
BASE_TENANT_NAME = "M8Flow Realm"

_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _create_all_tables() -> None:
    bind = op.get_bind()
    for metadata in alembic_target_metadata():
        metadata.create_all(bind, checkfirst=True)


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

        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))

        op.execute(sa.text(f"DROP POLICY IF EXISTS {tenant_policy} ON {table}"))
        op.execute(
            sa.text(
                f"CREATE POLICY {tenant_policy} ON {table} "
                f"FOR ALL USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
            )
        )

        # Super-admin cross-tenant read is SELECT-only.
        op.execute(sa.text(f"DROP POLICY IF EXISTS {bypass_policy} ON {table}"))
        op.execute(
            sa.text(
                f"CREATE POLICY {bypass_policy} ON {table} "
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
    final schema, so creating its standard Alembic marker here makes the host
    migration chain self-contained.  Never overwrite an existing marker: the
    breaking host migration either validates it or completes the final core
    handoff explicitly.
    """
    bind = op.get_bind()
    if sa.inspect(bind).has_table(CORE_VERSION_TABLE):
        return
    op.create_table(
        CORE_VERSION_TABLE,
        sa.Column("version_num", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("version_num"),
    )
    bind.execute(
        sa.text(f"INSERT INTO {CORE_VERSION_TABLE} (version_num) VALUES (:version)"),
        {"version": CORE_HEAD},
    )


def upgrade() -> None:
    _create_all_tables()
    _bootstrap_core_version_marker()
    _add_user_username_realm_unique()
    _enable_rls()
    _seed_base_tenant()


def downgrade() -> None:
    bind = op.get_bind()
    # drop_all resolves FK order itself; reverse the metadata list so host
    # tables (which FK into core/tenant tables) drop before their targets.
    for metadata in reversed(alembic_target_metadata()):
        metadata.drop_all(bind, checkfirst=True)
