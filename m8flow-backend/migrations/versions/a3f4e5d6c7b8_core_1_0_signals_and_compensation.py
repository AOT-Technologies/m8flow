"""Add core 1.0's signal registry and compensation journal tables.

m8flow-core 1.0 adds two revisions after the ``k2l3m4n5o6p7`` baseline the host
already carries: ``l3m4n5o6p7q8`` (signal publication registry) and
``m8f_671_compensation`` (compensation journal). The core wheel doesn't package
its Alembic scripts, so this ports them. Core reads ``signal_subscription``
every time it saves a process instance, so the tables must exist before the
host runs on core 1.0.

A database the baseline revision built against core 1.0 already has them (the
baseline runs ``create_all`` over the live ORM), so every step checks first.
Each new table gets the same tenant-isolation and super-admin read policies as
the other tenant-scoped tables.

The core marker in ``m8flow_core_alembic_version`` stays at ``k2l3m4n5o6p7``:
host migrations own the core schema after that handoff, and the earlier host
revisions that a self-healing replay re-runs require exactly that value.

Revision ID: a3f4e5d6c7b8
Revises: d1e2f3a4b5c6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3f4e5d6c7b8"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

_TENANT_RLS_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_RLS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"

# (index name, table) pairs core 1.0 adds so tenant-scoped foreign keys can
# reference (m8f_tenant_id, id).
_TENANT_ID_KEYS = (
    ("m8f_process_instance_tenant_id_key", "process_instance"),
    ("m8f_definition_tenant_id_key", "bpmn_process_definition"),
)
_COMPENSATION_TABLES = ("compensation_scope", "compensation_run", "compensation_record")
_NEW_TABLES = (
    "signal_registry_state",
    "signal_publication",
    "signal_subscription",
    "signal_delivery",
    *_COMPENSATION_TABLES,
)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(table: str, name: str) -> bool:
    return any(index["name"] == name for index in sa.inspect(op.get_bind()).get_indexes(table))


def _create_table(name: str, *elements: sa.SchemaItem) -> None:
    if not _has_table(name):
        op.create_table(name, *elements)


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if not _has_index(table, name):
        op.create_index(name, table, columns, unique=unique)


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


def _compensation_columns() -> list[sa.SchemaItem]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(255), sa.ForeignKey("m8flow_tenant.id"), nullable=False),
        sa.Column("process_instance_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["m8f_tenant_id", "process_instance_id"],
            ["process_instance.m8f_tenant_id", "process_instance.id"],
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _create_compensation_tables() -> None:
    """Port of core revision m8f_671_compensation."""
    _create_table(
        "compensation_scope",
        *_compensation_columns(),
        sa.Column("scope_id", sa.String(36), nullable=False),
        sa.Column("parent_scope_id", sa.String(36)),
        sa.Column("activity_id", sa.String(255), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("data_hash", sa.String(255), nullable=False),
        sa.UniqueConstraint(
            "m8f_tenant_id", "process_instance_id", "scope_id", name="m8f_compensation_scope_occurrence"
        ),
    )
    _create_table(
        "compensation_run",
        *_compensation_columns(),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("throw_task_guid", sa.String(36), nullable=False),
        sa.Column("scope_id", sa.String(36), nullable=False),
        sa.Column("wait_for_completion", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint(
            "m8f_tenant_id", "process_instance_id", "throw_task_guid", name="m8f_compensation_run_occurrence"
        ),
    )
    _create_table(
        "compensation_record",
        *_compensation_columns(),
        sa.Column("source_task_guid", sa.String(36), nullable=False),
        sa.Column("activity_id", sa.String(255), nullable=False),
        sa.Column("scope_id", sa.String(36), nullable=False),
        sa.Column("completion_sequence", sa.Integer(), nullable=False),
        sa.Column("handler_id", sa.String(255)),
        sa.Column("handler_task_guid", sa.String(36)),
        sa.Column("run_id", sa.String(36)),
        sa.Column("throw_task_guid", sa.String(36)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failure_details", sa.Text()),
        sa.Column("data_hash", sa.String(255), nullable=False),
        sa.Column("workflow_state_hash", sa.String(255)),
        sa.UniqueConstraint(
            "m8f_tenant_id",
            "process_instance_id",
            "source_task_guid",
            name="m8f_compensation_record_occurrence",
        ),
        sa.UniqueConstraint(
            "m8f_tenant_id",
            "process_instance_id",
            "completion_sequence",
            name="m8f_compensation_record_sequence",
        ),
    )
    for table in _COMPENSATION_TABLES:
        for column in ("m8f_tenant_id", "process_instance_id"):
            _create_index(f"ix_{table}_{column}", table, [column])


def _ensure_tenant_rls(table_name: str) -> None:
    """Apply the standard tenant policy pair on PostgreSQL tables."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    preparer = bind.dialect.identifier_preparer
    table = preparer.quote(table_name)
    tenant_policy = preparer.quote(f"{table_name}_tenant_isolation")
    bypass_policy = preparer.quote(f"{table_name}_super_admin_select")
    op.execute(sa.DDL(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {tenant_policy} ON {table}"))
    op.execute(
        sa.DDL(
            f"CREATE POLICY {tenant_policy} ON {table} FOR ALL "
            f"USING {_TENANT_RLS_PREDICATE} WITH CHECK {_TENANT_RLS_PREDICATE}"
        )
    )
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {bypass_policy} ON {table}"))
    op.execute(sa.DDL(f"CREATE POLICY {bypass_policy} ON {table} FOR SELECT USING {_BYPASS_RLS_PREDICATE}"))


def upgrade() -> None:
    for name, table in _TENANT_ID_KEYS:
        _create_index(name, table, ["m8f_tenant_id", "id"], unique=True)
    _create_signal_tables()
    _create_compensation_tables()
    for table in _NEW_TABLES:
        _ensure_tenant_rls(table)


def downgrade() -> None:
    for table in reversed(_NEW_TABLES):
        if _has_table(table):
            op.drop_table(table)
    for name, table in _TENANT_ID_KEYS:
        if _has_index(table, name):
            op.drop_index(name, table_name=table)
