"""Add core 1.0's signal registry tables.

m8flow-core 1.0 adds revision ``l3m4n5o6p7q8`` (signal publication registry)
after the ``k2l3m4n5o6p7`` baseline the host already carries; host revision
``fa8b9c0d1e2f`` covers core's compensation journal. The core wheel doesn't
package its Alembic scripts, so this ports the registry. Core reads
``signal_subscription`` every time it saves a process instance, so the tables
must exist before the host runs on core 1.0.

A database the baseline revision built against core 1.0 already has them (the
baseline runs ``create_all`` over the live ORM), so every step checks first.
The tables and tenant/id indexes this revision creates are recorded in
``m8flow_a3f4e5d6c7b8_ownership``, and downgrade drops only those: a table that
already existed keeps its rows, and indexes added to it stay. Each new table
gets the same tenant-isolation and super-admin read policies as the other
tenant-scoped tables. On a table that already existed, the ownership table also
records whether this revision turned RLS on and the definition of each policy
it replaced, and downgrade restores exactly that.

The core marker in ``m8flow_core_alembic_version`` stays at ``k2l3m4n5o6p7``:
host migrations own the core schema after that handoff, and the earlier host
revisions that a self-healing replay re-runs require exactly that value.

Revision ID: a3f4e5d6c7b8
Revises: d8e9f0a1b2c3
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

LOGGER = logging.getLogger("alembic.runtime.migration")

revision = "a3f4e5d6c7b8"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None

# Tables the signal registry references, all created by the baseline revision.
_PARENT_TABLES = ("m8flow_tenant", "process_instance", "bpmn_process_definition")
# object_name is a created table or index, ``rls:<table>`` when RLS was turned on
# for an existing table, or ``policy:<name>`` for a policy added to one, with
# restore_sql holding the CREATE POLICY for the definition it replaced, if any.
_OWNERSHIP = sa.table(
    f"m8flow_{revision}_ownership",
    sa.column("object_name", sa.String(63)),
    sa.column("restore_sql", sa.Text()),
)

_TENANT_RLS_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_RLS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"

# (index name, table) pairs core 1.0 adds so tenant-scoped foreign keys can
# reference (m8f_tenant_id, id).
_TENANT_ID_KEYS = (
    ("m8f_process_instance_tenant_id_key", "process_instance"),
    ("m8f_definition_tenant_id_key", "bpmn_process_definition"),
)
_NEW_TABLES = (
    "signal_registry_state",
    "signal_publication",
    "signal_subscription",
    "signal_delivery",
)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(table: str, name: str) -> bool:
    return any(index["name"] == name for index in sa.inspect(op.get_bind()).get_indexes(table))


def _index_exists(table: str, name: str, columns: list[str], *, unique: bool) -> bool:
    """True when ``table`` has ``name`` or an equivalent under another name.

    Equivalent means a full (not partial) index on exactly ``columns``, unique
    when ``unique`` is required, or a unique or primary key constraint on them.
    A baseline ``create_all`` or an earlier host revision may have named it.
    """
    inspector = sa.inspect(op.get_bind())
    for index in inspector.get_indexes(table):
        partial = any(key.endswith("_where") for key in index.get("dialect_options", {}))
        if index["name"] == name or (
            index["column_names"] == columns and not partial and (index["unique"] or not unique)
        ):
            return True
    keys = [constraint["column_names"] for constraint in inspector.get_unique_constraints(table)]
    keys.append(inspector.get_pk_constraint(table)["constrained_columns"])
    return columns in keys


def _recorded() -> set[str]:
    return set(op.get_bind().execute(sa.select(_OWNERSHIP.c.object_name)).scalars())


def _record_created(name: str, restore_sql: str | None = None) -> None:
    """Record ``name`` once; a rerun keeps the state from before the first run."""
    if name not in _recorded():
        op.get_bind().execute(_OWNERSHIP.insert().values(object_name=name, restore_sql=restore_sql))


def _create_table(name: str, *elements: sa.SchemaItem) -> None:
    if not _has_table(name):
        op.create_table(name, *elements)
        _record_created(name)


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> bool:
    """Create the index unless it or an equivalent exists; True if created."""
    if _index_exists(table, name, columns, unique=unique):
        return False
    op.create_index(name, table, columns, unique=unique)
    return True


def _pk(table: str) -> str:
    return f"pk_{table}"


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["m8f_tenant_id"], ["m8flow_tenant.id"], name=f"fk_{table}_m8f_tenant_id_m8flow_tenant"
    )


def _process_instance_fk(table: str, column: str = "process_instance_id") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["m8f_tenant_id", column],
        ["process_instance.m8f_tenant_id", "process_instance.id"],
        name=f"fk_{table}_m8f_tenant_id_process_instance",
    )


def _create_signal_tables() -> None:
    """Port of core revision l3m4n5o6p7q8."""
    _create_table(
        "signal_registry_state",
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        _tenant_fk("signal_registry_state"),
        sa.PrimaryKeyConstraint("m8f_tenant_id", name=_pk("signal_registry_state")),
    )
    _create_table(
        "signal_publication",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occurrence_id", sa.String(length=255), nullable=False),
        sa.Column("signal_name", sa.String(length=255), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("source_process_instance_id", sa.Integer(), nullable=True),
        sa.Column("source_task_guid", sa.String(length=36), nullable=True),
        sa.Column("published_by_user_id", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        _tenant_fk("signal_publication"),
        sa.PrimaryKeyConstraint("id", name=_pk("signal_publication")),
        _process_instance_fk("signal_publication", "source_process_instance_id"),
        sa.UniqueConstraint("m8f_tenant_id", "occurrence_id", name="uq_signal_publication_occurrence"),
        sa.UniqueConstraint("m8f_tenant_id", "id", name="uq_signal_publication_tenant_id"),
    )
    _create_index("ix_signal_publication_m8f_tenant_id", "signal_publication", ["m8f_tenant_id"])
    _create_table(
        "signal_subscription",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_key", sa.String(length=255), nullable=False),
        sa.Column("signal_name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("process_instance_id", sa.Integer(), nullable=True),
        sa.Column("definition_id", sa.Integer(), nullable=True),
        sa.Column("scope_id", sa.String(length=36), nullable=True),
        sa.Column("task_guid", sa.String(length=36), nullable=True),
        sa.Column("task_spec_name", sa.String(length=255), nullable=False),
        sa.Column("process_model_identifier", sa.String(length=255), nullable=True),
        sa.Column("repeatable", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("reserved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["m8f_tenant_id", "definition_id"],
            ["bpmn_process_definition.m8f_tenant_id", "bpmn_process_definition.id"],
            name="fk_signal_subscription_m8f_tenant_id_bpmn_process_definition",
        ),
        _tenant_fk("signal_subscription"),
        _process_instance_fk("signal_subscription"),
        sa.CheckConstraint(
            "kind IN ('start', 'catch', 'boundary', 'event_subprocess')",
            name="m8f_signal_subscription_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'start' AND definition_id IS NOT NULL AND process_instance_id IS NULL) OR "
            "(kind <> 'start' AND process_instance_id IS NOT NULL)",
            name="m8f_signal_subscription_references",
        ),
        sa.PrimaryKeyConstraint("id", name=_pk("signal_subscription")),
        sa.UniqueConstraint("m8f_tenant_id", "subscription_key", name="uq_signal_subscription_key"),
        sa.UniqueConstraint("m8f_tenant_id", "id", name="uq_signal_subscription_tenant_id"),
    )
    _create_index("ix_signal_subscription_m8f_tenant_id", "signal_subscription", ["m8f_tenant_id"])
    _create_index("ix_signal_subscription_match", "signal_subscription", ["m8f_tenant_id", "signal_name", "active"])
    _create_index("ix_signal_subscription_process_instance_id", "signal_subscription", ["process_instance_id"])
    _create_table(
        "signal_delivery",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("publication_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("process_instance_id", sa.Integer(), nullable=True),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        _tenant_fk("signal_delivery"),
        _process_instance_fk("signal_delivery"),
        sa.ForeignKeyConstraint(
            ["m8f_tenant_id", "publication_id"],
            ["signal_publication.m8f_tenant_id", "signal_publication.id"],
            name="fk_signal_delivery_m8f_tenant_id_signal_publication",
        ),
        sa.ForeignKeyConstraint(
            ["m8f_tenant_id", "subscription_id"],
            ["signal_subscription.m8f_tenant_id", "signal_subscription.id"],
            name="fk_signal_delivery_m8f_tenant_id_signal_subscription",
        ),
        sa.CheckConstraint("attempts >= 0", name="m8f_signal_delivery_attempts"),
        sa.CheckConstraint("status IN ('pending', 'delivered', 'skipped')", name="m8f_signal_delivery_status"),
        sa.PrimaryKeyConstraint("id", name=_pk("signal_delivery")),
        sa.UniqueConstraint(
            "m8f_tenant_id", "publication_id", "subscription_id", name="uq_signal_delivery_m8f_tenant_id"
        ),
    )
    _create_index("ix_signal_delivery_due", "signal_delivery", ["m8f_tenant_id", "status", "retry_at"])
    _create_index("ix_signal_delivery_m8f_tenant_id", "signal_delivery", ["m8f_tenant_id"])


def _policies(table_name: str) -> tuple[tuple[str, str], tuple[str, str]]:
    """The standard (policy name, CREATE POLICY body) pair for ``table_name``."""
    return (
        (
            f"{table_name}_tenant_isolation",
            f"FOR ALL USING {_TENANT_RLS_PREDICATE} WITH CHECK {_TENANT_RLS_PREDICATE}",
        ),
        (f"{table_name}_super_admin_select", f"FOR SELECT USING {_BYPASS_RLS_PREDICATE}"),
    )


def _current_policy_sql(table_name: str, policy_name: str) -> str | None:
    """CREATE POLICY that recreates the existing policy, or None if there is none."""
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT permissive, roles, cmd, qual, with_check FROM pg_policies "
            "WHERE schemaname = current_schema() AND tablename = :table AND policyname = :policy"
        ),
        {"table": table_name, "policy": policy_name},
    ).one_or_none()
    if row is None:
        return None
    quote = bind.dialect.identifier_preparer.quote
    roles = ", ".join("PUBLIC" if role == "public" else quote(role) for role in row.roles)
    sql = f"CREATE POLICY {quote(policy_name)} ON {quote(table_name)} AS {row.permissive} FOR {row.cmd} TO {roles}"
    if row.qual is not None:
        sql += f" USING ({row.qual})"
    if row.with_check is not None:
        sql += f" WITH CHECK ({row.with_check})"
    return sql


def _ensure_tenant_rls(table_name: str, *, existed: bool) -> None:
    """Apply the standard tenant policy pair on PostgreSQL tables.

    For a table that ``existed`` before this revision, record what changes so
    downgrade can put it back.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    quote = bind.dialect.identifier_preparer.quote
    table = quote(table_name)
    if existed and not bind.execute(
        sa.text("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(:table)"), {"table": table}
    ).scalar():
        _record_created(f"rls:{table_name}")
    op.execute(sa.DDL(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    for policy_name, body in _policies(table_name):
        if existed:
            _record_created(f"policy:{policy_name}", _current_policy_sql(table_name, policy_name))
        op.execute(sa.DDL(f"DROP POLICY IF EXISTS {quote(policy_name)} ON {table}"))
        op.execute(sa.DDL(f"CREATE POLICY {quote(policy_name)} ON {table} {body}"))


def _restore_tenant_rls(table_name: str, records: dict[str, str | None]) -> None:
    """Undo what ``_ensure_tenant_rls`` changed on a table this revision kept."""
    quote = op.get_bind().dialect.identifier_preparer.quote
    table = quote(table_name)
    for policy_name, _body in _policies(table_name):
        key = f"policy:{policy_name}"
        if key not in records:
            continue
        op.execute(sa.DDL(f"DROP POLICY IF EXISTS {quote(policy_name)} ON {table}"))
        if records[key] is not None:
            op.execute(sa.DDL(records[key]))
    if f"rls:{table_name}" in records:
        op.execute(sa.DDL(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))


def _require_parent_tables() -> None:
    missing = [name for name in _PARENT_TABLES if not _has_table(name)]
    if missing:
        raise RuntimeError(
            f"Migration {revision} cannot add the signal registry: missing table(s) "
            f"{', '.join(missing)}, which the baseline revision creates. Restore them, "
            "or migrate an empty database from base, then rerun the upgrade."
        )


def upgrade() -> None:
    _require_parent_tables()
    if not _has_table(_OWNERSHIP.name):
        op.create_table(
            _OWNERSHIP.name,
            sa.Column("object_name", sa.String(63), primary_key=True),
            sa.Column("restore_sql", sa.Text(), nullable=True),
        )
    for name, table in _TENANT_ID_KEYS:
        if _create_index(name, table, ["m8f_tenant_id", "id"], unique=True):
            _record_created(name)
    existing = {table for table in _NEW_TABLES if _has_table(table)} - _recorded()
    _create_signal_tables()
    for table in _NEW_TABLES:
        _ensure_tenant_rls(table, existed=table in existing)


def downgrade() -> None:
    if not _has_table(_OWNERSHIP.name):
        LOGGER.warning("Leaving the signal registry in place: %s has no record of what it created.", revision)
        return
    records = dict(op.get_bind().execute(sa.select(_OWNERSHIP.c.object_name, _OWNERSHIP.c.restore_sql)).all())
    created = set(records)
    for table in reversed(_NEW_TABLES):
        if table in created and _has_table(table):
            op.drop_table(table)
        elif _has_table(table):
            _restore_tenant_rls(table, records)
    for name, table in _TENANT_ID_KEYS:
        if name in created and _has_index(table, name):
            op.drop_index(name, table_name=table)
    op.drop_table(_OWNERSHIP.name)
