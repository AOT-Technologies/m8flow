"""Read side of the NATS event audit trail.

**Tenant scoping is explicit here.** Every query constrains the tenant itself; the only
way to read across tenants is ``all_tenants=True``, which the controller grants to
super-admins alone. (PostgreSQL RLS on ``m8f_tenant_id`` is the backstop, not the gate.)
"""

from __future__ import annotations

import logging

from sqlalchemy import Select, func, select

from m8flow_backend.config import nats_events_stream_name, nats_notifications_stream_name
from m8flow_backend.db import current_session
from m8flow_backend.errors import ApiError
from m8flow_backend.models import M8flowTenantModel
from m8flow_backend.models.nats_event_audit import (
    FAILURE_OUTCOMES,
    NatsEventAuditModel,
    NatsEventOutcome,
    NatsEventWorker,
)

logger = logging.getLogger("m8flow.nats.audit.query")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

VALID_OUTCOMES = frozenset(outcome.value for outcome in NatsEventOutcome)

_Audit = NatsEventAuditModel


def stream_for_worker(worker: str | None) -> str:
    """Which stream holds the payload for an audit row.

    Derived from the row's own ``worker``, never from the request: the row's bare sequence
    number is only meaningful within its own stream, so letting a caller name the stream
    would pair *their* row's sequence with whatever sits at that position elsewhere.
    """
    if worker == NatsEventWorker.notification_worker.value:
        return nats_notifications_stream_name()
    return nats_events_stream_name()


def _serialize(row: NatsEventAuditModel) -> dict:
    return {
        "id": row.id,
        "tenantId": row.m8f_tenant_id,
        "eventId": row.event_id,
        "worker": row.worker,
        "streamName": stream_for_worker(row.worker),
        "streamSeq": row.stream_seq,
        "processIdentifier": row.process_identifier,
        "username": row.username,
        "outcome": row.outcome,
        "duplicateCount": row.duplicate_count or 0,
        "errorMessage": row.error_message,
        "processInstanceId": row.process_instance_id,
        "queuedAtInSeconds": row.created_at_in_seconds,
        "completedAtInSeconds": row.completed_at_in_seconds,
        "updatedAtInSeconds": row.updated_at_in_seconds,
    }


class NatsEventAuditQueryService:
    @staticmethod
    def _scope(stmt: Select, tenant_id: str | None, all_tenants: bool) -> Select:
        """Apply the tenant constraint. Without a tenant and without ``all_tenants`` this
        refuses to run rather than silently returning every tenant's rows."""
        if all_tenants:
            return stmt
        if not tenant_id:
            raise ApiError(
                error_code="tenant_context_required",
                message="An active tenant is required to read NATS event history.",
                status_code=400,
            )
        return stmt.where(_Audit.m8f_tenant_id == tenant_id)

    @staticmethod
    def _filters(
        stmt: Select,
        *,
        outcome: str | None,
        process_identifier: str | None,
        username: str | None,
        event_id: str | None,
        worker: str | None,
        failures_only: bool,
        since_in_seconds: int | None,
        until_in_seconds: int | None,
    ) -> Select:
        if outcome:
            if outcome not in VALID_OUTCOMES:
                raise ApiError(error_code="invalid_outcome", message=f"Unknown outcome '{outcome}'.", status_code=400)
            stmt = stmt.where(_Audit.outcome == outcome)
        if failures_only:
            stmt = stmt.where(_Audit.outcome.in_(FAILURE_OUTCOMES))
        # Free-text search boxes: case-insensitive "contains". outcome/worker stay exact.
        if process_identifier:
            stmt = stmt.where(_Audit.process_identifier.ilike(f"%{process_identifier}%"))
        if username:
            stmt = stmt.where(_Audit.username.ilike(f"%{username}%"))
        if event_id:
            stmt = stmt.where(_Audit.event_id.ilike(f"%{event_id}%"))
        if worker:
            stmt = stmt.where(_Audit.worker == worker)
        # Queued time, not completion: an in-flight row has no completion time.
        if since_in_seconds is not None:
            stmt = stmt.where(_Audit.created_at_in_seconds >= since_in_seconds)
        if until_in_seconds is not None:
            stmt = stmt.where(_Audit.created_at_in_seconds <= until_in_seconds)
        return stmt

    @classmethod
    def list_events(
        cls,
        *,
        tenant_id: str | None,
        all_tenants: bool = False,
        outcome: str | None = None,
        process_identifier: str | None = None,
        username: str | None = None,
        event_id: str | None = None,
        worker: str | None = None,
        failures_only: bool = False,
        since_in_seconds: int | None = None,
        until_in_seconds: int | None = None,
        page: int = 1,
        per_page: int = DEFAULT_PAGE_SIZE,
    ) -> dict:
        session = current_session()
        stmt = cls._filters(
            cls._scope(select(_Audit), tenant_id, all_tenants),
            outcome=outcome,
            process_identifier=process_identifier,
            username=username,
            event_id=event_id,
            worker=worker,
            failures_only=failures_only,
            since_in_seconds=since_in_seconds,
            until_in_seconds=until_in_seconds,
        )
        page = max(1, int(page or 1))
        per_page = max(1, min(int(per_page or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = session.scalars(stmt.order_by(_Audit.id.desc()).limit(per_page).offset((page - 1) * per_page)).all()
        return {
            "results": [_serialize(row) for row in rows],
            "pagination": {
                "page": page,
                "perPage": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            },
        }

    @classmethod
    def get_event(cls, event_id: str, *, tenant_id: str | None, all_tenants: bool = False) -> dict:
        stmt = cls._scope(select(_Audit), tenant_id, all_tenants).where(_Audit.event_id == event_id)
        row = current_session().scalars(stmt.order_by(_Audit.id.desc())).first()
        if row is None:
            # Same 404 whether absent or another tenant's, so ids cannot be probed.
            raise ApiError(
                error_code="nats_event_not_found",
                message=f"No NATS event history for id '{event_id}'.",
                status_code=404,
            )
        return _serialize(row)

    @classmethod
    def summary(cls, *, tenant_id: str | None, all_tenants: bool = False) -> dict:
        """Counts by outcome, for the dashboard's summary cards."""
        session = current_session()
        rows = session.execute(
            cls._scope(select(_Audit.outcome, func.count(_Audit.id)), tenant_id, all_tenants).group_by(
                _Audit.outcome
            )
        ).all()
        by_outcome = {outcome: count for outcome, count in rows}
        duplicates = session.scalar(
            cls._scope(select(func.coalesce(func.sum(_Audit.duplicate_count), 0)), tenant_id, all_tenants)
        )
        return {
            "byOutcome": by_outcome,
            "total": sum(by_outcome.values()),
            "queued": by_outcome.get(NatsEventOutcome.queued.value, 0),
            "instantiated": by_outcome.get(NatsEventOutcome.instantiated.value, 0),
            "failed": sum(by_outcome.get(o, 0) for o in FAILURE_OUTCOMES),
            # Suppressed re-deliveries: a client double-firing, not a fault on our side.
            "duplicateDeliveries": int(duplicates or 0),
        }

    @classmethod
    def per_tenant(cls) -> list[dict]:
        """Backlog and outcome counts for every tenant. Super-admin only (caller-gated)."""
        session = current_session()
        counts = session.execute(
            select(
                _Audit.m8f_tenant_id,
                _Audit.outcome,
                func.count(_Audit.id),
                func.max(_Audit.updated_at_in_seconds),
            ).group_by(_Audit.m8f_tenant_id, _Audit.outcome)
        ).all()

        by_tenant: dict[str | None, dict] = {}
        for tenant_id, outcome, count, last_activity in counts:
            entry = by_tenant.setdefault(
                tenant_id,
                {
                    "tenantId": tenant_id,
                    "tenantSlug": None,
                    "queued": 0,
                    "instantiated": 0,
                    "failed": 0,
                    "total": 0,
                    "lastActivityInSeconds": 0,
                },
            )
            entry["total"] += count
            if outcome == NatsEventOutcome.queued.value:
                entry["queued"] += count
            elif outcome == NatsEventOutcome.instantiated.value:
                entry["instantiated"] += count
            elif outcome in FAILURE_OUTCOMES:
                entry["failed"] += count
            entry["lastActivityInSeconds"] = max(entry["lastActivityInSeconds"], last_activity or 0)

        tenant_ids = [tid for tid in by_tenant if tid]
        if tenant_ids:
            for tenant_id, slug in session.execute(
                select(M8flowTenantModel.id, M8flowTenantModel.slug).where(M8flowTenantModel.id.in_(tenant_ids))
            ).all():
                by_tenant[tenant_id]["tenantSlug"] = slug

        # Un-attributable rows (malformed subject): surfaced, not dropped.
        if None in by_tenant:
            by_tenant[None]["tenantSlug"] = "(unattributed)"

        return sorted(by_tenant.values(), key=lambda e: (-e["queued"], -e["failed"], e["tenantSlug"] or ""))
