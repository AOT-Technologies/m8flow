"""Unit tests for NatsEventAuditService (write side of the NATS event audit trail).

Covers: queued rows never downgrade a terminal outcome; outcomes update in place or
insert; NULL-tenant (un-attributable) messages; truncation; rule 1 (audit failures never
reach the caller); commit=False joins the caller's transaction via a SAVEPOINT; prune.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from m8flow_backend.auth.canonicalize import current_tenant_id_or_none
from m8flow_backend.auth.tenant_context import reset_context_tenant_id, set_context_tenant_id
from m8flow_backend.db import get_session_factory
from m8flow_backend.models import M8flowTenantModel
from m8flow_backend.models.nats_event_audit import (
    UNATTRIBUTED_TENANT_ID,
    NatsEventAuditModel,
    NatsEventOutcome,
    NatsEventWorker,
)
from m8flow_backend.services.nats_event_audit_service import (
    MAX_ERROR_MESSAGE_LENGTH,
    NatsEventAuditService,
)

SECONDS_PER_DAY = 24 * 60 * 60
TENANT = "tenant-1"


@pytest.fixture
def engine(db_engine):
    # pysqlite's implicit transaction handling breaks SAVEPOINT; restore standard
    # behaviour (SQLAlchemy's pysqlite recipe) so these tests mean what they would on
    # PostgreSQL. dispose() so pooled connections pick the listeners up.
    @event.listens_for(db_engine, "connect")
    def _connect(dbapi_connection, _record):  # pragma: no cover - fixture wiring
        dbapi_connection.isolation_level = None

    @event.listens_for(db_engine, "begin")
    def _begin(conn):  # pragma: no cover - fixture wiring
        conn.exec_driver_sql("BEGIN")

    db_engine.dispose()
    return db_engine


def _session() -> Session:
    return get_session_factory()()


def _rows() -> list[NatsEventAuditModel]:
    with _session() as session:
        return list(session.scalars(select(NatsEventAuditModel).order_by(NatsEventAuditModel.id)))


def _boom(*_a, **_k):
    raise RuntimeError("database is on fire")


class TestRecordQueued:
    def test_inserts_a_queued_row(self, engine):
        NatsEventAuditService.record_queued(
            tenant_id=TENANT, event_id="evt-1", process_identifier="group/proc", username="alice"
        )

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].m8f_tenant_id == TENANT
        assert rows[0].outcome == NatsEventOutcome.queued.value
        assert rows[0].process_identifier == "group/proc"
        assert rows[0].username == "alice"
        assert rows[0].completed_at_in_seconds is None
        assert rows[0].created_at_in_seconds > 0
        assert rows[0].is_pending()

    def test_does_not_downgrade_an_existing_terminal_outcome(self, engine):
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT, event_id="evt-1", outcome=NatsEventOutcome.instantiated.value, process_instance_id=99
        )
        NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="evt-1")

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].outcome == NatsEventOutcome.instantiated.value
        assert rows[0].process_instance_id == 99


class TestRecordOutcome:
    def test_updates_the_queued_row_in_place(self, engine):
        NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="evt-1", process_identifier="group/proc")
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT,
            event_id="evt-1",
            outcome=NatsEventOutcome.instantiated.value,
            process_instance_id=4242,
            stream_seq=9_223_372_036_854_775_000,
        )

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].outcome == NatsEventOutcome.instantiated.value
        assert rows[0].process_instance_id == 4242
        assert rows[0].stream_seq == 9_223_372_036_854_775_000
        assert rows[0].completed_at_in_seconds is not None
        assert rows[0].process_identifier == "group/proc"

    def test_inserts_when_there_is_no_queued_row(self, engine):
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT,
            event_id="evt-direct",
            outcome=NatsEventOutcome.rejected_auth.value,
            error_message="invalid api_key",
        )

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].error_message == "invalid api_key"
        assert rows[0].is_failure()

    def test_records_an_unattributable_message_under_the_placeholder_tenant(self, engine):
        # Not NULL: under RLS a NULL tenant never matches the transaction's, so the row
        # could not be written at all.
        NatsEventAuditService.record_outcome(
            tenant_id=None, event_id=None, outcome=NatsEventOutcome.invalid_payload.value
        )

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].m8f_tenant_id == UNATTRIBUTED_TENANT_ID

    def test_two_unattributable_messages_both_get_rows(self, engine):
        for _ in range(2):
            NatsEventAuditService.record_outcome(
                tenant_id=None, event_id=None, outcome=NatsEventOutcome.invalid_payload.value
            )
        assert len(_rows()) == 2

    def test_truncates_a_long_error_message(self, engine):
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT,
            event_id="evt-1",
            outcome=NatsEventOutcome.transient_error.value,
            error_message="x" * (MAX_ERROR_MESSAGE_LENGTH * 2),
        )
        stored = _rows()[0].error_message
        assert len(stored) == MAX_ERROR_MESSAGE_LENGTH
        assert stored.endswith("...")

    def test_same_event_id_in_another_tenant_is_a_separate_row(self, engine):
        NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="evt-1")
        NatsEventAuditService.record_outcome(
            tenant_id="tenant-2", event_id="evt-1", outcome=NatsEventOutcome.instantiated.value
        )
        by_tenant = {row.m8f_tenant_id: row.outcome for row in _rows()}
        assert by_tenant == {TENANT: "queued", "tenant-2": "instantiated"}


class TestRecordDuplicate:
    def test_counts_on_the_original_row_without_touching_its_outcome(self, engine):
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT, event_id="evt-1", outcome=NatsEventOutcome.instantiated.value, process_instance_id=7
        )
        NatsEventAuditService.record_duplicate(tenant_id=TENANT, event_id="evt-1")

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].outcome == NatsEventOutcome.instantiated.value
        assert rows[0].process_instance_id == 7
        assert rows[0].duplicate_count == 1

    def test_a_retry_loop_increments_rather_than_adding_rows(self, engine):
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT, event_id="evt-1", outcome=NatsEventOutcome.instantiated.value
        )
        for _ in range(5):
            NatsEventAuditService.record_duplicate(tenant_id=TENANT, event_id="evt-1")

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].duplicate_count == 5

    def test_bumping_the_count_moves_the_updated_timestamp(self, engine):
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT, event_id="evt-1", outcome=NatsEventOutcome.instantiated.value
        )
        with _session() as session:
            session.execute(text("UPDATE m8flow_nats_event_audit SET updated_at_in_seconds = 1000"))
            session.commit()

        NatsEventAuditService.record_duplicate(tenant_id=TENANT, event_id="evt-1")

        assert _rows()[0].updated_at_in_seconds > 1000

    def test_writes_a_duplicate_row_when_the_original_is_gone(self, engine):
        NatsEventAuditService.record_duplicate(tenant_id=TENANT, event_id="evt-unknown")

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].outcome == NatsEventOutcome.duplicate.value
        assert rows[0].duplicate_count == 1

    def test_a_fresh_row_starts_at_zero_duplicates(self, engine):
        NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="evt-1")
        assert _rows()[0].duplicate_count == 0


class TestNeverBreaksTheCaller:
    """Rule 1: recording what happened must not change what happens."""

    @pytest.mark.parametrize(
        "call",
        [
            lambda: NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="evt-1"),
            lambda: NatsEventAuditService.record_outcome(
                tenant_id=TENANT, event_id="evt-1", outcome=NatsEventOutcome.instantiated.value
            ),
            lambda: NatsEventAuditService.record_duplicate(tenant_id=TENANT, event_id="evt-1"),
        ],
        ids=["queued", "outcome", "duplicate"],
    )
    def test_swallows_database_errors(self, engine, monkeypatch, call):
        monkeypatch.setattr(Session, "commit", _boom)
        call()  # must not raise

    def test_swallows_a_unique_violation_from_a_racing_writer(self, engine, monkeypatch):
        # Another writer inserted the row between this lookup and this insert.
        NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="evt-1")
        monkeypatch.setattr(NatsEventAuditService, "_find", staticmethod(lambda *_a, **_k: None))

        NatsEventAuditService.record_outcome(
            tenant_id=TENANT, event_id="evt-1", outcome=NatsEventOutcome.instantiated.value
        )  # must not raise

    def test_prune_swallows_database_errors(self, engine, monkeypatch):
        monkeypatch.setattr(Session, "commit", _boom)
        assert NatsEventAuditService.prune(retention_days=1) == 0

    def test_committing_writes_do_not_touch_the_callers_session(self, engine):
        """An audit write in its own session must not commit the caller's pending work."""
        caller = _session()
        caller.add(M8flowTenantModel(id="tenant-2", name="Two", slug="two"))
        NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="evt-1")
        caller.rollback()
        caller.close()

        with _session() as session:
            assert session.get(M8flowTenantModel, "tenant-2") is None
        assert len(_rows()) == 1

    def test_an_unwritable_audit_row_does_not_take_the_callers_work_with_it(self, engine, monkeypatch):
        """commit=False writes inside a SAVEPOINT: a failure rolls back alone."""
        real_apply = NatsEventAuditService._apply_outcome.__func__

        def _apply_then_fail(cls, session, **fields):
            real_apply(cls, session, **fields)
            raise RuntimeError("audit row is unwritable")

        monkeypatch.setattr(NatsEventAuditService, "_apply_outcome", classmethod(_apply_then_fail))

        caller = _session()
        caller.add(M8flowTenantModel(id="tenant-2", name="Two", slug="two"))
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT,
            event_id="evt-bad",
            outcome=NatsEventOutcome.instantiated.value,
            commit=False,
            session=caller,
        )
        caller.commit()
        caller.close()

        with _session() as session:
            assert session.get(M8flowTenantModel, "tenant-2") is not None
        assert _rows() == []


class TestCommitFalseJoinsTheCallerTransaction:
    def test_row_is_visible_only_after_the_caller_commits(self, engine):
        caller = _session()
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT,
            event_id="evt-1",
            outcome=NatsEventOutcome.instantiated.value,
            process_instance_id=11,
            commit=False,
            session=caller,
        )
        assert _rows() == []
        caller.commit()
        caller.close()

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].process_instance_id == 11

    def test_caller_rollback_discards_the_audit_row(self, engine):
        caller = _session()
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT,
            event_id="evt-1",
            outcome=NatsEventOutcome.instantiated.value,
            commit=False,
            session=caller,
        )
        caller.rollback()
        caller.close()

        assert _rows() == []


class TestPrune:
    @staticmethod
    def _terminal_row(event_id: str, completed_at: int) -> None:
        with _session() as session:
            session.add(
                NatsEventAuditModel(
                    m8f_tenant_id=TENANT,
                    event_id=event_id,
                    worker=NatsEventWorker.consumer.value,
                    outcome=NatsEventOutcome.instantiated.value,
                    completed_at_in_seconds=completed_at,
                )
            )
            session.commit()

    def test_removes_rows_past_the_retention_window(self, engine):
        now = int(time.time())
        self._terminal_row("old", now - 100 * SECONDS_PER_DAY)
        self._terminal_row("recent", now - 10 * SECONDS_PER_DAY)

        assert NatsEventAuditService.prune(retention_days=90) == 1
        assert [r.event_id for r in _rows()] == ["recent"]

    def test_never_prunes_an_in_flight_row(self, engine):
        NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="still-queued")

        assert NatsEventAuditService.prune(retention_days=1) == 0
        assert len(_rows()) == 1

    def test_zero_retention_disables_pruning(self, engine):
        self._terminal_row("ancient", 0)

        assert NatsEventAuditService.prune(retention_days=0) == 0
        assert len(_rows()) == 1


class TestARecordedSuccessIsFinal:
    def _outcome(self, outcome: NatsEventOutcome, **kw) -> None:
        NatsEventAuditService.record_outcome(tenant_id=TENANT, event_id="evt-1", outcome=outcome.value, **kw)

    def test_a_late_failure_does_not_clobber_the_success(self, engine):
        self._outcome(NatsEventOutcome.instantiated, process_instance_id=99)
        self._outcome(NatsEventOutcome.transient_error, error_message="publish ack timed out")

        row = _rows()[0]
        assert row.outcome == NatsEventOutcome.instantiated.value
        assert row.process_instance_id == 99
        assert row.error_message is None

    def test_a_retried_failure_may_still_reach_success(self, engine):
        self._outcome(NatsEventOutcome.transient_error, error_message="db briefly unreachable")
        self._outcome(NatsEventOutcome.instantiated, process_instance_id=7)

        row = _rows()[0]
        assert row.outcome == NatsEventOutcome.instantiated.value
        assert row.process_instance_id == 7

    def test_one_failure_may_be_refined_into_another(self, engine):
        self._outcome(NatsEventOutcome.transient_error)
        self._outcome(NatsEventOutcome.model_not_found)
        assert _rows()[0].outcome == NatsEventOutcome.model_not_found.value

    def test_a_terminal_row_cannot_be_pushed_back_to_queued(self, engine):
        self._outcome(NatsEventOutcome.rejected_scope)
        self._outcome(NatsEventOutcome.queued)
        assert _rows()[0].outcome == NatsEventOutcome.rejected_scope.value

    def test_repeating_the_same_outcome_still_updates_metadata(self, engine):
        self._outcome(NatsEventOutcome.instantiated)
        self._outcome(NatsEventOutcome.instantiated, process_instance_id=1234)
        assert _rows()[0].process_instance_id == 1234


class TestAnUnattributableEvent:
    """A message with no tenant is recorded under a placeholder tenant, so it updates in
    place and counts duplicates like any other event."""

    def test_is_updated_in_place(self, engine):
        NatsEventAuditService.record_outcome(
            tenant_id=None, event_id="evt-x", outcome=NatsEventOutcome.transient_error.value
        )
        NatsEventAuditService.record_outcome(
            tenant_id=None, event_id="evt-x", outcome=NatsEventOutcome.model_not_found.value
        )

        assert [r.outcome for r in _rows()] == [NatsEventOutcome.model_not_found.value]

    def test_counts_duplicate_deliveries(self, engine):
        NatsEventAuditService.record_outcome(
            tenant_id=None, event_id="evt-x", outcome=NatsEventOutcome.invalid_payload.value
        )
        NatsEventAuditService.record_duplicate(tenant_id=None, event_id="evt-x")

        assert [r.duplicate_count for r in _rows()] == [1]


@contextmanager
def _as_tenant(tenant_id: str):
    token = set_context_tenant_id(tenant_id)
    try:
        yield
    finally:
        reset_context_tenant_id(token)


@pytest.fixture
def rls(engine):
    """PostgreSQL's tenant policy, emulated on SQLite: a transaction may only write,
    change or delete rows of its own tenant. The tenant is current_tenant_id_or_none(),
    the value the after_begin hook hands PostgreSQL as app.current_tenant."""

    @event.listens_for(engine, "connect")
    def _register(dbapi_connection, _record):  # pragma: no cover - fixture wiring
        dbapi_connection.create_function("app_current_tenant", 0, current_tenant_id_or_none)

    engine.dispose()
    table = NatsEventAuditModel.__tablename__
    # "IS NOT 1" keeps PostgreSQL's "=": a NULL on either side never matches.
    denied = "(m8f_tenant_id = app_current_tenant()) IS NOT 1"
    reject = "BEGIN SELECT RAISE(ABORT, 'row-level security'); END"
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"CREATE TRIGGER rls_insert BEFORE INSERT ON {table} WHEN {denied.replace('m8f', 'NEW.m8f')} {reject}"
        )
        connection.exec_driver_sql(
            f"CREATE TRIGGER rls_update BEFORE UPDATE ON {table} "
            f"WHEN {denied.replace('m8f', 'OLD.m8f')} OR {denied.replace('m8f', 'NEW.m8f')} {reject}"
        )
        # USING hides other tenants' rows from a DELETE rather than failing it.
        connection.exec_driver_sql(
            f"CREATE TRIGGER rls_delete BEFORE DELETE ON {table} "
            f"WHEN {denied.replace('m8f', 'OLD.m8f')} BEGIN SELECT RAISE(IGNORE); END"
        )
    return engine


class TestWorkerWritesUnderRowLevelSecurity:
    """Worker code has no request tenant, so every write must carry its row's tenant into
    its own transaction, or PostgreSQL rejects it and the audit trail silently stops."""

    def test_a_worker_resolves_a_queued_row(self, rls):
        with _as_tenant(TENANT):
            NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="e1")

        NatsEventAuditService.record_outcome(
            tenant_id=TENANT, event_id="e1", outcome=NatsEventOutcome.rejected_auth.value
        )

        assert [r.outcome for r in _rows()] == [NatsEventOutcome.rejected_auth.value]

    def test_a_worker_counts_a_duplicate(self, rls):
        with _as_tenant(TENANT):
            NatsEventAuditService.record_outcome(
                tenant_id=TENANT, event_id="e1", outcome=NatsEventOutcome.instantiated.value
            )

        NatsEventAuditService.record_duplicate(tenant_id=TENANT, event_id="e1")

        assert [r.duplicate_count for r in _rows()] == [1]

    def test_a_worker_records_an_unattributable_message(self, rls):
        NatsEventAuditService.record_outcome(
            tenant_id=None, event_id=None, outcome=NatsEventOutcome.invalid_payload.value
        )

        assert [r.outcome for r in _rows()] == [NatsEventOutcome.invalid_payload.value]

    def test_prune_reaches_every_tenant(self, rls):
        old = int(time.time()) - 100 * SECONDS_PER_DAY
        with _session() as session:
            session.add_all(
                [M8flowTenantModel(id="t-a", name="A", slug="a"), M8flowTenantModel(id="t-b", name="B", slug="b")]
            )
            session.commit()
        for tenant_id in ("t-a", "t-b"):
            with _as_tenant(tenant_id):
                NatsEventAuditService.record_outcome(
                    tenant_id=tenant_id,
                    event_id="old",
                    outcome=NatsEventOutcome.instantiated.value,
                    completed_at_in_seconds=old,
                )

        assert NatsEventAuditService.prune(retention_days=90) == 2
        assert _rows() == []


class TestInsertOnly:
    """For a message whose sender is not verified yet, tenant and event id are only claims."""

    def test_never_rewrites_an_existing_row(self, engine):
        NatsEventAuditService.record_queued(tenant_id=TENANT, event_id="victim-evt")

        NatsEventAuditService.record_outcome(
            tenant_id=TENANT,
            event_id="victim-evt",
            outcome=NatsEventOutcome.rejected_auth.value,
            stream_seq=999,
            insert_only=True,
        )

        assert [(r.outcome, r.stream_seq) for r in _rows()] == [(NatsEventOutcome.queued.value, None)]

    def test_records_a_new_row(self, engine):
        NatsEventAuditService.record_outcome(
            tenant_id=TENANT, event_id="evt-1", outcome=NatsEventOutcome.rejected_auth.value, insert_only=True
        )

        assert [(r.event_id, r.outcome) for r in _rows()] == [("evt-1", NatsEventOutcome.rejected_auth.value)]
