"""Add m8flow_nats_event_audit table.

Records what became of each NATS message: its outcome, the failure reason, and the
process instance it created. The consumer currently logs every terminal outcome and then
ACKs the message, so a rejected or unparseable event leaves no queryable trace once log
retention rolls.

Purely additive: creates one new table and touches no existing data.

Revision ID: q0j1k2l3m4n5
Revises: p9i0j1k2l3m4
Create Date: 2026-07-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "q0j1k2l3m4n5"
down_revision = "p9i0j1k2l3m4"
branch_labels = None
depends_on = None

AUDIT_TABLE = "m8flow_nats_event_audit"
TENANT_INDEX = "ix_m8flow_nats_event_audit_tenant_id"
OUTCOME_INDEX = "ix_m8flow_nats_event_audit_outcome"
TENANT_OUTCOME_INDEX = "ix_m8flow_nats_event_audit_tenant_outcome"
TENANT_COMPLETED_INDEX = "ix_m8flow_nats_event_audit_tenant_completed"
UNIQUE_CONSTRAINT = "uq_m8flow_nats_event_audit_tenant_event_worker"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade():
    if _table_exists(AUDIT_TABLE):
        return

    op.create_table(
        AUDIT_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        # Named tenant_id, not m8f_tenant_id, on purpose: the automatic tenant machinery
        # in tenant_scoping_patch keys off that column name to stamp the ambient tenant on
        # insert, which would mis-attribute un-attributable messages. See the model
        # docstring. Nullable so a message with a malformed subject — exactly the failure
        # that is invisible today — is still recorded.
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("worker", sa.String(length=32), nullable=False),
        # BigInteger: JetStream stream sequences are uint64.
        sa.Column("stream_seq", sa.BigInteger(), nullable=True),
        sa.Column("process_identifier", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        # Extra deliveries of this same event id, suppressed by the dedup guard. Counted
        # on the original row rather than written as new rows, so a client stuck in a
        # retry loop cannot grow the table without bound.
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        # Deliberately not a ForeignKey: audit rows must outlive the instances they name.
        sa.Column("process_instance_id", sa.Integer(), nullable=True),
        sa.Column("completed_at_in_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["m8flow_tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "event_id", "worker", name=UNIQUE_CONSTRAINT),
    )
    op.create_index(op.f(TENANT_INDEX), AUDIT_TABLE, ["tenant_id"], unique=False)
    op.create_index(op.f(OUTCOME_INDEX), AUDIT_TABLE, ["outcome"], unique=False)
    op.create_index(TENANT_OUTCOME_INDEX, AUDIT_TABLE, ["tenant_id", "outcome"], unique=False)
    op.create_index(
        TENANT_COMPLETED_INDEX,
        AUDIT_TABLE,
        ["tenant_id", "completed_at_in_seconds"],
        unique=False,
    )


def downgrade():
    if not _table_exists(AUDIT_TABLE):
        return

    op.drop_index(TENANT_COMPLETED_INDEX, table_name=AUDIT_TABLE)
    op.drop_index(TENANT_OUTCOME_INDEX, table_name=AUDIT_TABLE)
    op.drop_index(op.f(OUTCOME_INDEX), table_name=AUDIT_TABLE)
    op.drop_index(op.f(TENANT_INDEX), table_name=AUDIT_TABLE)
    op.drop_table(AUDIT_TABLE)
