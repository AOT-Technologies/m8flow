"""Read side of the NATS event audit trail.

**Tenant scoping is explicit here and nowhere else.** ``NatsEventAuditModel`` deliberately
does not inherit ``M8fTenantScopedMixin`` — see the note in the model — so none of the
automatic filtering in ``tenant_scoping_patch`` applies to this table. Every query in this
module must therefore constrain the tenant itself, and the only way to read across tenants
is to ask for it by passing ``all_tenants=True``, which the controller grants to
super-admins alone.
"""

from __future__ import annotations

import logging

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.models.nats_event_audit import (
    FAILURE_OUTCOMES,
    NatsEventAuditModel,
    NatsEventOutcome,
)

logger = logging.getLogger("m8flow.nats.audit.query")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

VALID_OUTCOMES = frozenset(NatsEventOutcome.list())


def _serialize(row: NatsEventAuditModel) -> dict:
    return {
        "id": row.id,
        "tenantId": row.tenant_id,
        "eventId": row.event_id,
        "worker": row.worker,
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
    def _scoped_query(tenant_id: str | None, all_tenants: bool):
        """Base query with the tenant constraint applied.

        ``all_tenants`` is the only escape hatch and the controller gates it on
        super-admin. Without a tenant and without that flag this refuses to run rather than
        silently returning every tenant's rows.
        """
        query = NatsEventAuditModel.query
        if all_tenants:
            return query
        if not tenant_id:
            raise ApiError(
                error_code="tenant_context_required",
                message="An active tenant is required to read NATS event history.",
                status_code=400,
            )
        return query.filter(NatsEventAuditModel.tenant_id == tenant_id)

    @classmethod
    def _apply_filters(
        cls,
        query,
        *,
        outcome: str | None,
        process_identifier: str | None,
        username: str | None,
        event_id: str | None,
        worker: str | None,
        failures_only: bool,
        since_in_seconds: int | None,
        until_in_seconds: int | None,
    ):
        if outcome:
            if outcome not in VALID_OUTCOMES:
                raise ApiError(
                    error_code="invalid_outcome",
                    message=f"Unknown outcome '{outcome}'.",
                    status_code=400,
                )
            query = query.filter(NatsEventAuditModel.outcome == outcome)
        if failures_only:
            query = query.filter(NatsEventAuditModel.outcome.in_(FAILURE_OUTCOMES))
        if process_identifier:
            query = query.filter(
                NatsEventAuditModel.process_identifier == process_identifier
            )
        if username:
            query = query.filter(NatsEventAuditModel.username == username)
        if event_id:
            query = query.filter(NatsEventAuditModel.event_id == event_id)
        if worker:
            query = query.filter(NatsEventAuditModel.worker == worker)
        # Filter on queued time, not completion: an in-flight row has no completion time
        # and a date range that hid it would make the backlog look empty.
        if since_in_seconds is not None:
            query = query.filter(NatsEventAuditModel.created_at_in_seconds >= since_in_seconds)
        if until_in_seconds is not None:
            query = query.filter(NatsEventAuditModel.created_at_in_seconds <= until_in_seconds)
        return query

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
        query = cls._apply_filters(
            cls._scoped_query(tenant_id, all_tenants),
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
        total = query.count()

        rows = (
            query.order_by(NatsEventAuditModel.id.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
            .all()
        )

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
    def get_event(
        cls, event_id: str, *, tenant_id: str | None, all_tenants: bool = False
    ) -> dict:
        row = (
            cls._scoped_query(tenant_id, all_tenants)
            .filter(NatsEventAuditModel.event_id == event_id)
            .order_by(NatsEventAuditModel.id.desc())
            .first()
        )
        if row is None:
            # Deliberately the same 404 whether the row is absent or belongs to another
            # tenant, so this cannot be used to probe for other tenants' event ids.
            raise ApiError(
                error_code="nats_event_not_found",
                message=f"No NATS event history for id '{event_id}'.",
                status_code=404,
            )
        return _serialize(row)

    @classmethod
    def summary(cls, *, tenant_id: str | None, all_tenants: bool = False) -> dict:
        """Counts by outcome, for the dashboard's summary cards."""
        query = cls._scoped_query(tenant_id, all_tenants)
        rows = (
            query.with_entities(
                NatsEventAuditModel.outcome, db.func.count(NatsEventAuditModel.id)
            )
            .group_by(NatsEventAuditModel.outcome)
            .all()
        )

        by_outcome = {outcome: count for outcome, count in rows}
        duplicates = (
            query.with_entities(
                db.func.coalesce(db.func.sum(NatsEventAuditModel.duplicate_count), 0)
            ).scalar()
            or 0
        )

        return {
            "byOutcome": by_outcome,
            "total": sum(by_outcome.values()),
            "queued": by_outcome.get(NatsEventOutcome.queued.value, 0),
            "instantiated": by_outcome.get(NatsEventOutcome.instantiated.value, 0),
            "failed": sum(by_outcome.get(o, 0) for o in FAILURE_OUTCOMES),
            # Suppressed re-deliveries, which point at a client double-firing rather than
            # at anything wrong on our side.
            "duplicateDeliveries": int(duplicates),
        }

    @classmethod
    def per_tenant(cls) -> list[dict]:
        """Backlog and outcome counts for every tenant. Super-admin only.

        JetStream reports num_pending per *consumer*, and one durable serves every tenant,
        so ``/jsz`` cannot break the backlog down this way — these counts can, because the
        audit row is written per event with its tenant attached.
        """
        counts = (
            NatsEventAuditModel.query.with_entities(
                NatsEventAuditModel.tenant_id,
                NatsEventAuditModel.outcome,
                db.func.count(NatsEventAuditModel.id),
                db.func.max(NatsEventAuditModel.updated_at_in_seconds),
            )
            .group_by(NatsEventAuditModel.tenant_id, NatsEventAuditModel.outcome)
            .all()
        )

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
            entry["lastActivityInSeconds"] = max(
                entry["lastActivityInSeconds"], last_activity or 0
            )

        # Resolve slugs in one query rather than per row.
        tenant_ids = [tid for tid in by_tenant if tid]
        if tenant_ids:
            for tenant in M8flowTenantModel.query.filter(
                M8flowTenantModel.id.in_(tenant_ids)
            ).all():
                by_tenant[tenant.id]["tenantSlug"] = tenant.slug

        # Un-attributable rows (malformed subject) group under a null tenant. Surfaced
        # rather than dropped: they are the failures nothing else can show.
        if None in by_tenant:
            by_tenant[None]["tenantSlug"] = "(unattributed)"

        return sorted(
            by_tenant.values(),
            key=lambda e: (-e["queued"], -e["failed"], e["tenantSlug"] or ""),
        )
