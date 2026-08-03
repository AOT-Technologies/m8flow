"""Records what became of each NATS message.

The consumer logs every terminal outcome and then ACKs the message, so a rejected or
unparseable event leaves no queryable trace once log retention rolls. This service is the
single place that writes those outcomes down.

Two rules govern every call:

1. **A write here must never change message handling.** All public methods swallow their
   own errors and log instead. Monitoring must not become a new way for event processing
   to fail.
2. **A terminal outcome is never downgraded back to ``queued``.** The publish side and the
   consumer race by nature — the consumer can finish before ``publish_event`` returns — so
   ``record_queued`` only ever inserts a row that does not already exist.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from spiffworkflow_backend.models.db import db

from m8flow_backend.models.nats_event_audit import (
    NatsEventAuditModel,
    NatsEventOutcome,
    NatsEventWorker,
)

logger = logging.getLogger("m8flow.nats.audit")

# Long enough to keep a useful traceback tail, short enough that a pathological
# exception cannot bloat the table. The column itself is Text, so this is a display
# guard rather than a storage limit.
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


class NatsEventAuditService:
    """Write-side of the NATS event audit trail."""

    @staticmethod
    def _find(tenant_id: str | None, event_id: str | None, worker: str) -> NatsEventAuditModel | None:
        """Locate an existing row for this (tenant, event, worker).

        Returns None when ``event_id`` is absent: without it there is nothing stable to
        correlate on, so such messages always get a fresh row.
        """
        if not event_id:
            return None
        return NatsEventAuditModel.query.filter_by(
            tenant_id=tenant_id, event_id=event_id, worker=worker
        ).one_or_none()

    @classmethod
    def record_queued(
        cls,
        *,
        tenant_id: str | None,
        event_id: str,
        worker: str = NatsEventWorker.consumer.value,
        process_identifier: str | None = None,
        username: str | None = None,
        commit: bool = True,
    ) -> None:
        """Record a message as published and awaiting processing.

        Called *before* the publish so the row exists while the message is genuinely in
        flight; counting these per tenant is what makes per-tenant backlog an indexed
        query rather than a filtered ephemeral consumer per tenant per refresh.

        A no-op when a row already exists, so a late call can never overwrite a terminal
        outcome the consumer has already written.
        """
        try:
            if cls._find(tenant_id, event_id, worker) is not None:
                return

            db.session.add(
                NatsEventAuditModel(
                    tenant_id=tenant_id,
                    event_id=event_id,
                    worker=worker,
                    outcome=NatsEventOutcome.queued.value,
                    process_identifier=process_identifier,
                    username=username,
                )
            )
            if commit:
                db.session.commit()
        except IntegrityError:
            # Another writer inserted the same (tenant, event, worker) first. That row is
            # at least as current as this one, so there is nothing to do.
            db.session.rollback()
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception(
                "nats audit: failed to record queued event_id=%s tenant=%s", event_id, tenant_id
            )
        except Exception:
            logger.exception(
                "nats audit: unexpected error recording queued event_id=%s tenant=%s",
                event_id,
                tenant_id,
            )

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
    ) -> None:
        """Record the terminal disposition of a message.

        Updates the ``queued`` row written at publish time when there is one, and inserts
        a fresh row otherwise — a message published outside the backend (``publisher.py``
        talks to NATS directly) has no queued row, and neither does a redelivery whose
        original row was pruned.

        Pass ``commit=False`` to join the caller's transaction. The consumer uses this on
        the success path so the audit row and the process instance commit together, and an
        instance can never exist without its row. In that mode the write happens inside a
        SAVEPOINT: if the audit row turns out to be unwritable it rolls back to the
        savepoint and the caller's work still commits, because rule 1 outranks atomicity.

        Duplicate deliveries do not come through here — see ``record_duplicate``.
        """
        try:
            if commit:
                cls._apply_outcome(
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
                )
                db.session.commit()
                return

            with db.session.begin_nested():
                cls._apply_outcome(
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
                )
        except SQLAlchemyError:
            if commit:
                db.session.rollback()
            logger.exception(
                "nats audit: failed to record outcome=%s event_id=%s tenant=%s",
                outcome,
                event_id,
                tenant_id,
            )
        except Exception:
            if commit:
                db.session.rollback()
            logger.exception(
                "nats audit: unexpected error recording outcome=%s event_id=%s tenant=%s",
                outcome,
                event_id,
                tenant_id,
            )

    @classmethod
    def _apply_outcome(
        cls,
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
    ) -> None:
        """Insert-or-update the row. Caller owns the transaction boundary."""
        row = cls._find(tenant_id, event_id, worker)
        if row is None:
            row = NatsEventAuditModel(
                tenant_id=tenant_id, event_id=event_id, worker=worker, outcome=outcome
            )
            db.session.add(row)

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
        """Record that the dedup guard suppressed another delivery of this event.

        The unique key is (tenant, event, worker), so a duplicate has no row of its own —
        it carries the *same* event id as the original. Writing an outcome here would
        replace the original's ``instantiated`` and destroy the record of the run that
        actually happened, so instead the original row's ``duplicate_count`` is bumped and
        its outcome left alone. Counting rather than inserting also means a client stuck in
        a retry loop cannot grow the table without bound.

        When no original row exists — it was pruned, or the event was published straight to
        NATS by ``publisher.py`` and so never got a queued row — a fresh row is written with
        outcome ``duplicate``, because a suppressed delivery is all we know about it.
        """
        try:
            row = cls._find(tenant_id, event_id, worker)
            if row is None:
                db.session.add(
                    NatsEventAuditModel(
                        tenant_id=tenant_id,
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
                # Outcome deliberately untouched. updated_at_in_seconds moves on the
                # increment, which is what makes "last duplicated at" answerable.
                row.duplicate_count = (row.duplicate_count or 0) + 1

            db.session.commit()
        except IntegrityError:
            # Another writer inserted the row between the lookup and the insert; the
            # duplicate is already accounted for on their row.
            db.session.rollback()
        except Exception:
            db.session.rollback()
            logger.exception(
                "nats audit: failed to record duplicate event_id=%s tenant=%s", event_id, tenant_id
            )

    @staticmethod
    def prune(retention_days: int) -> int:
        """Delete completed rows older than the retention window.

        Only terminal rows are pruned: a ``queued`` row with no completion time may still
        be genuinely in flight behind a backlogged consumer, and deleting it would make
        the backlog count wrong.

        Returns the number of rows deleted, or 0 on failure (never raises — the caller is
        a background sweep that must keep running).
        """
        try:
            if retention_days <= 0:
                return 0
            cutoff = _now_in_seconds() - (retention_days * 24 * 60 * 60)
            deleted = (
                NatsEventAuditModel.query.filter(
                    NatsEventAuditModel.completed_at_in_seconds.isnot(None),
                    NatsEventAuditModel.completed_at_in_seconds < cutoff,
                ).delete(synchronize_session=False)
            )
            db.session.commit()
            if deleted:
                logger.info("nats audit: pruned %s row(s) older than %s day(s).", deleted, retention_days)
            return deleted
        except Exception:
            db.session.rollback()
            logger.exception("nats audit: prune failed")
            return 0
