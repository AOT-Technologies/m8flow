from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from spiffworkflow_backend.helpers.spiff_enum import SpiffEnum
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db

from m8flow_backend.models.audit_mixin import AuditDateTimeMixin


class NatsEventWorker(SpiffEnum):
    """Which process handled (or will handle) the message."""

    consumer = "consumer"
    notification_worker = "notification_worker"
    # A message published by hand from the NATS monitoring UI, recorded so every
    # manual publish is attributable to a user.
    manual = "manual"


class NatsEventOutcome(SpiffEnum):
    """Terminal disposition of a NATS message, or ``queued`` while in flight."""

    # Published but not yet handled. Counting these per tenant is what gives a
    # per-tenant backlog figure: JetStream reports num_pending per *consumer*, and a
    # single durable serves every tenant, so /jsz cannot break the backlog down.
    queued = "queued"
    # Success: a process instance was created.
    instantiated = "instantiated"
    # Suppressed by the KV dedup guard.
    duplicate = "duplicate"
    # Body was not valid JSON, or required fields / subject format were missing.
    invalid_payload = "invalid_payload"
    # api_key missing, unknown, expired or revoked.
    rejected_auth = "rejected_auth"
    # Valid key, but not scoped for the requested process.
    rejected_scope = "rejected_scope"
    # The key's tenant did not match the tenant the event claimed.
    tenant_mismatch = "tenant_mismatch"
    # The initiating username did not resolve to a user in the tenant.
    user_not_found = "user_not_found"
    # The requested process model does not exist.
    model_not_found = "model_not_found"
    # Anything else (e.g. a DB failure); the only class that may be retryable.
    transient_error = "transient_error"


# Outcomes that mean the message is still owed processing.
PENDING_OUTCOMES = (NatsEventOutcome.queued.value,)

# Outcomes that represent a message that never produced a process instance. Used for
# the failure counts on the monitoring dashboard.
FAILURE_OUTCOMES = (
    NatsEventOutcome.invalid_payload.value,
    NatsEventOutcome.rejected_auth.value,
    NatsEventOutcome.rejected_scope.value,
    NatsEventOutcome.tenant_mismatch.value,
    NatsEventOutcome.user_not_found.value,
    NatsEventOutcome.model_not_found.value,
    NatsEventOutcome.transient_error.value,
)


@dataclass
class NatsEventAuditModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """One row per NATS message per worker: what arrived, and what became of it.

    The consumer currently logs every terminal outcome and then ACKs the message, so a
    rejected or unparseable event leaves no queryable trace once log retention rolls
    (see ``m8flow-nats-consumer/consumer.py``). This table is that trace.

    Payloads are deliberately NOT stored. All m8flow streams are created without
    ``max_age``/``max_msgs`` limits, so JetStream retains every message indefinitely —
    ``stream_seq`` points at the single copy already in NATS and the payload is fetched
    on demand, rather than duplicating tenant business data into Postgres.

    NOTE ON THE TENANT COLUMN NAME. This table deliberately uses ``tenant_id`` rather
    than the repo-wide ``m8f_tenant_id`` / ``M8fTenantScopedMixin`` convention, because
    both halves of the automatic tenant machinery in
    ``m8flow_backend.services.tenant_scoping_patch`` are wrong for an operations log:

    - ``_set_tenant_on_flush`` keys off the *column name* ``m8f_tenant_id`` and stamps
      the ambient tenant onto any row where it is falsy. On an audit table that means a
      message that could not be attributed would be silently recorded against whichever
      tenant happened to be in context. A mis-attributed audit row is worse than a
      missing one.
    - ``_tenant_scope_queries`` auto-filters every query on ``M8fTenantScopedMixin``
      subclasses to the ambient tenant, and ``is_tenant_context_exempt_request()`` does
      not exempt super-admins. That would silently reduce the cross-tenant views this
      table exists to provide (per-tenant backlog roll-up, all-tenant event history) to
      the single tenant the super-admin has selected.

    Tenant isolation is therefore enforced explicitly at the query/route layer instead:
    callers always filter by tenant, and only super-admin may read across tenants. The
    ForeignKey to ``m8flow_tenant`` is kept, so referential integrity still holds.
    """

    __tablename__ = "m8flow_nats_event_audit"
    __table_args__ = (
        # Publish inserts, consume updates, and a redelivery updates rather than
        # duplicating. NULL tenant/event ids compare as distinct in Postgres, so
        # un-attributable messages (below) may legitimately produce one row per
        # delivery attempt — informative rather than harmful.
        db.UniqueConstraint(
            "tenant_id", "event_id", "worker", name="uq_m8flow_nats_event_audit_tenant_event_worker"
        ),
        # Backlog and failure counts per tenant.
        db.Index("ix_m8flow_nats_event_audit_tenant_outcome", "tenant_id", "outcome"),
        # The paged, time-ordered history list.
        db.Index(
            "ix_m8flow_nats_event_audit_tenant_completed", "tenant_id", "completed_at_in_seconds"
        ),
    )

    id: int = db.Column(db.Integer, primary_key=True)

    # Nullable: a message whose subject is malformed cannot be attributed to any tenant,
    # and those are precisely the failures that are invisible today. Recording them with
    # a NULL tenant keeps them visible to a super-admin, while tenant-scoped queries
    # (which always filter on tenant_id) never return them.
    tenant_id: Optional[str] = db.Column(
        db.String(255), db.ForeignKey("m8flow_tenant.id"), nullable=True, index=True
    )

    # The publisher-generated event id used for idempotency. Nullable: the consumer
    # tolerates events with no id (it warns that dedup cannot be guaranteed).
    event_id: Optional[str] = db.Column(db.String(255), nullable=True)

    worker: str = db.Column(db.String(32), nullable=False)

    # JetStream stream sequence — the pointer used to fetch the payload on demand.
    # BigInteger because stream sequences are uint64 and would overflow a 32-bit int.
    stream_seq: Optional[int] = db.Column(db.BigInteger, nullable=True)

    # Denormalized so the history list renders without one NATS fetch per row.
    process_identifier: Optional[str] = db.Column(db.String(255), nullable=True)
    username: Optional[str] = db.Column(db.String(255), nullable=True)

    outcome: str = db.Column(
        db.String(32), nullable=False, default=NatsEventOutcome.queued.value, index=True
    )

    # Extra deliveries of this same event id that the dedup guard suppressed. Because the
    # unique key is (tenant, event, worker) there is only one row per event, so a duplicate
    # is counted here instead of overwriting the outcome of the run that actually happened.
    # Counting rather than inserting also keeps a client stuck in a retry loop from growing
    # the table without bound. ``updated_at_in_seconds`` moves on each increment, which is
    # what makes "most recently duplicated at" answerable without another column.
    duplicate_count: int = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    # Text, not a bounded varchar: an exception message can exceed a few KB and a fixed
    # varchar truncates the insert (the same trap hit by external_form_url). The service
    # layer truncates to a sane display length before writing.
    error_message: Optional[str] = db.Column(db.Text, nullable=True)

    # Intentionally not a ForeignKey: audit rows must outlive the process instances they
    # reference, and an FK would either block instance deletion or cascade the row away.
    process_instance_id: Optional[int] = db.Column(db.Integer, nullable=True)

    # NULL until the message reaches a terminal outcome. ``created_at_in_seconds`` from
    # AuditDateTimeMixin is the queued/published time, so no separate column is needed.
    completed_at_in_seconds: Optional[int] = db.Column(db.Integer, nullable=True)

    def is_pending(self) -> bool:
        return self.outcome in PENDING_OUTCOMES

    def is_failure(self) -> bool:
        return self.outcome in FAILURE_OUTCOMES

    def __repr__(self) -> str:
        return (
            f"<NatsEventAuditModel(event_id={self.event_id}, tenant_id={self.tenant_id},"
            f" worker={self.worker}, outcome={self.outcome})>"
        )
