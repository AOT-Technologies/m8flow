"""Add m8flow_nats_event_audit table (NATS monitoring event audit trail).

Records what became of each NATS message: outcome, failure reason, and the process
instance it created. Purely additive.

Idempotent on purpose: the root revision ``1518b05122bc`` builds every table from the
live ORM metadata, so on a fresh database the table (and its RLS policies) already exist
by the time this runs. On a database upgraded from the root before this model existed,
this creates the table and applies the same tenant-isolation + SELECT-only super-admin
RLS policy pair the root applies to every ``m8f_tenant_id`` table.

Revision ID: 2c7e9a41d5f3
Revises: 1518b05122bc
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "2c7e9a41d5f3"
down_revision = "1518b05122bc"
branch_labels = None
depends_on = None

AUDIT_TABLE = "m8flow_nats_event_audit"
# Names match what HostBase's naming convention gives the model.
PRIMARY_KEY_NAME = "_".join(("pk", "host", AUDIT_TABLE))
TENANT_INDEX = "ix_host_m8flow_nats_event_audit_m8f_tenant_id"
OUTCOME_INDEX = "ix_host_m8flow_nats_event_audit_outcome"
TENANT_OUTCOME_INDEX = "ix_m8flow_nats_event_audit_tenant_outcome"
TENANT_COMPLETED_INDEX = "ix_m8flow_nats_event_audit_tenant_completed"
UNIQUE_CONSTRAINT = "uq_m8flow_nats_event_audit_tenant_event_worker"

# Same predicates as the root revision.
_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls() -> None:
    if not _is_postgres():
        return
    tenant_policy = f"{AUDIT_TABLE}_tenant_isolation"
    bypass_policy = f"{AUDIT_TABLE}_super_admin_select"
    op.execute(sa.text(f"ALTER TABLE {AUDIT_TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {tenant_policy} ON {AUDIT_TABLE}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {tenant_policy} ON {AUDIT_TABLE} "
            f"FOR ALL USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
        )
    )
    op.execute(sa.text(f"DROP POLICY IF EXISTS {bypass_policy} ON {AUDIT_TABLE}"))
    op.execute(
        sa.text(f"CREATE POLICY {bypass_policy} ON {AUDIT_TABLE} FOR SELECT USING {_BYPASS_PREDICATE}")
    )


def upgrade() -> None:
    if not _table_exists(AUDIT_TABLE):
        op.create_table(
            AUDIT_TABLE,
            sa.Column("id", sa.Integer(), nullable=False),
            # Nullable: a message with a malformed subject is still recorded.
            sa.Column("m8f_tenant_id", sa.String(length=255), nullable=True),
            sa.Column("event_id", sa.String(length=255), nullable=True),
            sa.Column("worker", sa.String(length=32), nullable=False),
            # BigInteger: JetStream stream sequences are uint64.
            sa.Column("stream_seq", sa.BigInteger(), nullable=True),
            sa.Column("process_identifier", sa.String(length=255), nullable=True),
            sa.Column("username", sa.String(length=255), nullable=True),
            sa.Column("outcome", sa.String(length=32), nullable=False),
            sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            # Deliberately not a ForeignKey: audit rows outlive the instances they name.
            sa.Column("process_instance_id", sa.Integer(), nullable=True),
            sa.Column("completed_at_in_seconds", sa.Integer(), nullable=True),
            sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
            sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id", name=PRIMARY_KEY_NAME),
            sa.UniqueConstraint("m8f_tenant_id", "event_id", "worker", name=UNIQUE_CONSTRAINT),
        )
        op.create_index(TENANT_INDEX, AUDIT_TABLE, ["m8f_tenant_id"], unique=False)
        op.create_index(OUTCOME_INDEX, AUDIT_TABLE, ["outcome"], unique=False)
        op.create_index(TENANT_OUTCOME_INDEX, AUDIT_TABLE, ["m8f_tenant_id", "outcome"], unique=False)
        op.create_index(
            TENANT_COMPLETED_INDEX, AUDIT_TABLE, ["m8f_tenant_id", "completed_at_in_seconds"], unique=False
        )
    _enable_rls()


def downgrade() -> None:
    # Dropping the table drops its indexes and RLS policies with it.
    if _table_exists(AUDIT_TABLE):
        op.drop_table(AUDIT_TABLE)
