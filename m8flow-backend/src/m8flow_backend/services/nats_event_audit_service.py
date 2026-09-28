"""Records what became of each NATS message.

Two rules govern every call:

1. **A write here must never change message handling.** All public methods swallow their
   own errors and log instead.
2. **A terminal outcome is never downgraded back to ``queued``.** The publisher and the
   consumer race by nature, so ``record_queued`` only ever inserts a row that does not
   already exist.

Committing writes (the default) run in their own short-lived session, so an audit failure
can never roll back, or prematurely commit, the caller's request transaction. That session's
transaction carries the row's own tenant, because PostgreSQL RLS admits a write only when
the two match and worker code has no request tenant to lend it. Pass
``commit=False`` (with ``session=``) to join the caller's transaction instead; the write
then happens inside a SAVEPOINT so an unwritable audit row does not poison it.

The keyword is ``tenant_id`` (the tenant UUID); it is stored in ``m8f_tenant_id``, and
``None`` is stored as ``UNATTRIBUTED_TENANT_ID``.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from m8flow_backend.auth.tenant_context import reset_context_tenant_id, set_context_tenant_id
from m8flow_backend.db import current_session, session_scope
from m8flow_backend.models import M8flowTenantModel
from m8flow_backend.models.nats_event_audit import (
    UNATTRIBUTED_TENANT_ID,
    NatsEventAuditModel,
    NatsEventOutcome,
    NatsEventWorker,
)

logger = logging.getLogger("m8flow.nats.audit")

# Display guard; the column itself is Text.
MAX_ERROR_MESSAGE_LENGTH = 2000


def _now_in_seconds() -> int:
    return int(time.time())


def _truncate(message: str | None) -> str | None:
    if message is None:
        return None
    text = str(message)
    if len(text) <= MAX_ERROR_MESSAGE_LENGTH:
        return text
    return text[: MAX_ERROR_MESSAGE_LENGTH - 3] + "..."


def _may_overwrite(current: str | None, incoming: str) -> bool:
    """A recorded success is final; failures stay replaceable (a retried transient error
    may later succeed); nothing ever goes back to ``queued``."""
    if current == incoming:
        return True
    if current == NatsEventOutcome.instantiated.value:
        return False
    return incoming != NatsEventOutcome.queued.value


@contextmanager
def _tenant_session(tenant_id: str) -> Iterator[Session]:
    """A committing session whose transaction carries ``tenant_id`` into PostgreSQL RLS."""
    token = set_context_tenant_id(tenant_id)
    try:
        with session_scope() as session:
            yield session
    finally:
        reset_context_tenant_id(token)


class NatsEventAuditService:
    """Write-side of the NATS event audit trail."""

    @staticmethod
    def _find(session: Session, tenant_id: str, event_id: str | None, worker: str) -> NatsEventAuditModel | None:
        """The row for (tenant, event, worker); None when there is no event id."""
        if not event_id:
            return None
        return session.scalars(
            select(NatsEventAuditModel)
            .where(
                NatsEventAuditModel.m8f_tenant_id == tenant_id,
                NatsEventAuditModel.event_id == event_id,
                NatsEventAuditModel.worker == worker,
            )
            .order_by(NatsEventAuditModel.id.desc())
        ).first()

    @classmethod
    def record_queued(
        cls,
        *,
        tenant_id: str | None,
        event_id: str,
        worker: str = NatsEventWorker.consumer.value,
        process_identifier: str | None = None,
        username: str | None = None,
    ) -> None:
        """Record a message as published and awaiting processing. Called *before* the
        publish; a no-op when a row already exists."""
        tenant_id = tenant_id or UNATTRIBUTED_TENANT_ID
        try:
            with _tenant_session(tenant_id) as session:
                if cls._find(session, tenant_id, event_id, worker) is not None:
                    return
                session.add(
                    NatsEventAuditModel(
                        m8f_tenant_id=tenant_id,
                        event_id=event_id,
                        worker=worker,
                        outcome=NatsEventOutcome.queued.value,
                        process_identifier=process_identifier,
                        username=username,
                    )
                )
        except IntegrityError:
            # Another writer inserted the same row first; theirs is at least as current.
            pass
        except Exception:
            logger.exception("nats audit: failed to record queued event_id=%s tenant=%s", event_id, tenant_id)

    @classmethod
    def record_outcome(
        cls,
        *,
        tenant_id: str | None,
        event_id: str | None,
        outcome: str,
        worker: str = NatsEventWorker.consumer.value,
        error_message: str | None = None,
        process_instance_id: int | None = None,
        stream_seq: int | None = None,
        process_identifier: str | None = None,
        username: str | None = None,
        completed_at_in_seconds: int | None = None,
        commit: bool = True,
        session: Session | None = None,
        insert_only: bool = False,
    ) -> None:
        """Record the terminal disposition of a message.

        Updates the ``queued`` row when there is one, inserts otherwise. With
        ``commit=False`` the write joins ``session`` (default: the current request
        session) inside a SAVEPOINT, so the audit row and e.g. a created process instance
        commit together, while a failed audit write still leaves the caller's work intact.

        ``insert_only`` writes a new row and never touches an existing one. It is for a
        message whose sender is not verified yet, whose tenant and event id are only
        claims: a forged message must not rewrite another tenant's history.
        """
        tenant_id = tenant_id or UNATTRIBUTED_TENANT_ID
        fields = dict(
            tenant_id=tenant_id,
            event_id=event_id,
            worker=worker,
            outcome=outcome,
            error_message=error_message,
            process_instance_id=process_instance_id,
            stream_seq=stream_seq,
            process_identifier=process_identifier,
            username=username,
            completed_at_in_seconds=completed_at_in_seconds,
            insert_only=insert_only,
        )
        try:
            if commit:
                with _tenant_session(tenant_id) as own:
                    cls._apply_outcome(own, **fields)
                return
            joined = session or current_session()
            with joined.begin_nested():
                cls._apply_outcome(joined, **fields)
        except Exception as error:
            if insert_only and isinstance(error, IntegrityError):
                # A row for this event already exists; an unverified claim leaves it alone.
                logger.warning(
                    "nats audit: kept the existing row for unverified outcome=%s event_id=%s tenant=%s",
                    outcome,
                    event_id,
                    tenant_id,
                )
                return
            logger.exception(
                "nats audit: failed to record outcome=%s event_id=%s tenant=%s", outcome, event_id, tenant_id
            )

    @classmethod
    def _apply_outcome(
        cls,
        session: Session,
        *,
        tenant_id: str | None,
        event_id: str | None,
        worker: str,
        outcome: str,
        error_message: str | None,
        process_instance_id: int | None,
        stream_seq: int | None,
        process_identifier: str | None,
        username: str | None,
        completed_at_in_seconds: int | None,
        insert_only: bool,
    ) -> None:
        row = None if insert_only else cls._find(session, tenant_id, event_id, worker)
        if row is None:
            row = NatsEventAuditModel(m8f_tenant_id=tenant_id, event_id=event_id, worker=worker, outcome=outcome)
            session.add(row)
        elif not _may_overwrite(row.outcome, outcome):
            logger.warning(
                "nats audit: refusing to overwrite outcome=%s with outcome=%s for event_id=%s tenant=%s",
                row.outcome,
                outcome,
                event_id,
                tenant_id,
            )
            return

        row.outcome = outcome
        row.error_message = _truncate(error_message)
        if process_instance_id is not None:
            row.process_instance_id = process_instance_id
        if stream_seq is not None:
            row.stream_seq = stream_seq
        if process_identifier is not None:
            row.process_identifier = process_identifier
        if username is not None:
            row.username = username
        row.completed_at_in_seconds = completed_at_in_seconds or _now_in_seconds()
        session.flush()

    @classmethod
    def record_duplicate(
        cls,
        *,
        tenant_id: str | None,
        event_id: str | None,
        worker: str = NatsEventWorker.consumer.value,
        stream_seq: int | None = None,
        process_identifier: str | None = None,
        username: str | None = None,
    ) -> None:
        """Bump ``duplicate_count`` on the original row (its outcome is left alone), or,
        when no original exists, write a fresh ``duplicate`` row."""
        tenant_id = tenant_id or UNATTRIBUTED_TENANT_ID
        try:
            with _tenant_session(tenant_id) as session:
                row = cls._find(session, tenant_id, event_id, worker)
                if row is None:
                    session.add(
                        NatsEventAuditModel(
                            m8f_tenant_id=tenant_id,
                            event_id=event_id,
                            worker=worker,
                            outcome=NatsEventOutcome.duplicate.value,
                            duplicate_count=1,
                            stream_seq=stream_seq,
                            process_identifier=process_identifier,
                            username=username,
                            completed_at_in_seconds=_now_in_seconds(),
                        )
                    )
                else:
                    row.duplicate_count = (row.duplicate_count or 0) + 1
        except IntegrityError:
            # Another writer inserted the row between lookup and insert.
            pass
        except Exception:
            logger.exception("nats audit: failed to record duplicate event_id=%s tenant=%s", event_id, tenant_id)

    @staticmethod
    def prune(retention_days: int) -> int:
        """Delete terminal rows older than the retention window; queued rows are kept
        because they may still be in flight. Returns rows deleted; never raises.

        One DELETE per tenant, each under that tenant, because RLS lets a transaction see
        only its own tenant's rows. The unattributed pass also clears legacy NULL rows,
        which only exist where RLS is not enforced.
        """
        if retention_days <= 0:
            return 0
        cutoff = _now_in_seconds() - retention_days * 24 * 60 * 60
        try:
            with session_scope() as session:
                tenant_ids = set(session.scalars(select(M8flowTenantModel.id)))
                # Rows outlive their tenant; where RLS is not enforced they show up here too.
                tenant_ids |= set(session.scalars(select(NatsEventAuditModel.m8f_tenant_id).distinct()))
            tenant_ids.discard(None)
            tenant_ids.add(UNATTRIBUTED_TENANT_ID)
            deleted = 0
            # ponytail: one transaction per tenant; a BYPASSRLS maintenance role could do it in one.
            for tenant_id in sorted(tenant_ids):
                owned = NatsEventAuditModel.m8f_tenant_id == tenant_id
                if tenant_id == UNATTRIBUTED_TENANT_ID:
                    owned = owned | NatsEventAuditModel.m8f_tenant_id.is_(None)
                with _tenant_session(tenant_id) as session:
                    result = session.execute(
                        delete(NatsEventAuditModel).where(
                            owned,
                            NatsEventAuditModel.completed_at_in_seconds.is_not(None),
                            NatsEventAuditModel.completed_at_in_seconds < cutoff,
                        )
                    )
                    deleted += result.rowcount or 0
            if deleted:
                logger.info("nats audit: pruned %s row(s) older than %s day(s).", deleted, retention_days)
            return deleted
        except Exception:
            logger.exception("nats audit: prune failed")
            return 0
