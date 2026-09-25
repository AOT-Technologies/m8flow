from __future__ import annotations

import enum
import time

from sqlalchemy import BigInteger, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase


class NatsEventWorker(str, enum.Enum):
    """Which process handled (or will handle) the message."""

    consumer = "consumer"
    notification_worker = "notification_worker"
    # A message published by hand from the NATS monitoring UI.
    manual = "manual"


class NatsEventOutcome(str, enum.Enum):
    """Terminal disposition of a NATS message, or ``queued`` while in flight."""

    # Published but not yet handled. Counting these per tenant gives a per-tenant backlog:
    # JetStream reports num_pending per *consumer*, and one durable serves every tenant.
    queued = "queued"
    instantiated = "instantiated"
    duplicate = "duplicate"
    invalid_payload = "invalid_payload"
    rejected_auth = "rejected_auth"
    rejected_scope = "rejected_scope"
    tenant_mismatch = "tenant_mismatch"
    user_not_found = "user_not_found"
    model_not_found = "model_not_found"
    # Anything else (e.g. a DB failure); the only class that may be retryable.
    transient_error = "transient_error"


PENDING_OUTCOMES = (NatsEventOutcome.queued.value,)

# Outcomes that never produced a process instance.
FAILURE_OUTCOMES = (
    NatsEventOutcome.invalid_payload.value,
    NatsEventOutcome.rejected_auth.value,
    NatsEventOutcome.rejected_scope.value,
    NatsEventOutcome.tenant_mismatch.value,
    NatsEventOutcome.user_not_found.value,
    NatsEventOutcome.model_not_found.value,
    NatsEventOutcome.transient_error.value,
)


def _now() -> int:
    return int(time.time())


class NatsEventAuditModel(HostBase):
    """One row per NATS message per worker: what arrived, and what became of it.

    Payloads are NOT stored: ``stream_seq`` points at the copy JetStream already retains.

    ``m8f_tenant_id`` is nullable: a message whose subject cannot be attributed to a tenant
    is still recorded (visible to super-admin only). The column name follows the repo
    convention so the root migration's PostgreSQL RLS policy covers this table; reads are
    additionally tenant-filtered explicitly in ``NatsEventAuditQueryService``. No FK to
    ``m8flow_tenant`` (it lives in core metadata) and none to process instances, so audit
    rows outlive what they reference. Schema matches migrations/versions/
    2c7e9a41d5f3_add_nats_event_audit.py -- keep the two in sync.
    """

    __tablename__ = "m8flow_nats_event_audit"
    __table_args__ = (
        # NULL tenant/event ids compare as distinct, so un-attributable messages may
        # produce one row per delivery attempt.
        UniqueConstraint(
            "m8f_tenant_id", "event_id", "worker", name="uq_m8flow_nats_event_audit_tenant_event_worker"
        ),
        Index("ix_m8flow_nats_event_audit_tenant_outcome", "m8f_tenant_id", "outcome"),
        Index("ix_m8flow_nats_event_audit_tenant_completed", "m8f_tenant_id", "completed_at_in_seconds"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    m8f_tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    worker: Mapped[str] = mapped_column(String(32), nullable=False)
    # uint64 JetStream sequence.
    stream_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    process_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outcome: Mapped[str] = mapped_column(
        String(32), nullable=False, default=NatsEventOutcome.queued.value, index=True
    )
    # Suppressed re-deliveries of this same event id, counted instead of new rows.
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    process_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL until terminal; created_at_in_seconds is the queued/published time.
    completed_at_in_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=_now)
    updated_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, onupdate=_now)

    def is_pending(self) -> bool:
        return self.outcome in PENDING_OUTCOMES

    def is_failure(self) -> bool:
        return self.outcome in FAILURE_OUTCOMES


__all__ = [
    "FAILURE_OUTCOMES",
    "NatsEventAuditModel",
    "NatsEventOutcome",
    "NatsEventWorker",
    "PENDING_OUTCOMES",
]
