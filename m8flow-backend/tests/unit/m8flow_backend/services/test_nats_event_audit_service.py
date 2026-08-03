"""Unit tests for NatsEventAuditService.

Tests cover:
- record_queued inserts a queued row and never downgrades a terminal outcome
- record_outcome updates the queued row in place, and inserts when there is none
- only_if_absent protects the original run's outcome from a duplicate delivery
- un-attributable messages are recorded with a NULL tenant
- error messages are truncated
- an audit-write failure never propagates to the caller (rule 1)
- commit=False joins the caller's transaction, and a bad row rolls back alone
- prune removes old terminal rows but never in-flight ones
"""
import sys
import time
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import event, text

# Setup path for imports (mirror the models tests)
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from m8flow_backend.models.nats_event_audit import (  # noqa: E402
    NatsEventAuditModel,
    NatsEventOutcome,
    NatsEventWorker,
)
from m8flow_backend.services.nats_event_audit_service import (  # noqa: E402
    MAX_ERROR_MESSAGE_LENGTH,
    NatsEventAuditService,
)
from spiffworkflow_backend.models.db import add_listeners, db  # noqa: E402

SECONDS_PER_DAY = 24 * 60 * 60


@pytest.fixture
def app():
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        # pysqlite ships with implicit transaction handling that silently breaks SAVEPOINT,
        # and leaves foreign keys unenforced unless asked. Left alone, the transaction tests
        # below would fail — and the foreign-key test would pass — for reasons that have
        # nothing to do with this code. Restore standard behaviour (the recipe from
        # SQLAlchemy's pysqlite notes) so these tests mean on sqlite what they mean on
        # PostgreSQL, where the same assertions were verified against a live database.
        @event.listens_for(db.engine, "connect")
        def _sqlite_connect(dbapi_connection, _record):  # pragma: no cover - fixture wiring
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        @event.listens_for(db.engine, "begin")
        def _sqlite_begin(conn):  # pragma: no cover - fixture wiring
            conn.exec_driver_sql("BEGIN")

        db.create_all()
        add_listeners()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def tenant(app):
    tenant = M8flowTenantModel(
        id="tenant-1",
        name="Tenant One",
        slug="tenant-one",
        status=TenantStatus.ACTIVE,
        created_by="admin",
        modified_by="admin",
    )
    db.session.add(tenant)
    db.session.commit()
    return tenant


def _rows():
    return NatsEventAuditModel.query.all()


class TestRecordQueued:
    def test_inserts_a_queued_row(self, app, tenant):
        NatsEventAuditService.record_queued(
            tenant_id=tenant.id,
            event_id="evt-1",
            process_identifier="group/proc",
            username="alice",
        )

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].outcome == NatsEventOutcome.queued.value
        assert rows[0].process_identifier == "group/proc"
        assert rows[0].username == "alice"
        assert rows[0].completed_at_in_seconds is None
        assert rows[0].is_pending()

    def test_does_not_downgrade_an_existing_terminal_outcome(self, app, tenant):
        """The consumer can finish before publish_event returns; a late queued write
        must not replace the outcome it already recorded."""
        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id,
            event_id="evt-1",
            outcome=NatsEventOutcome.instantiated.value,
            process_instance_id=99,
        )

        NatsEventAuditService.record_queued(tenant_id=tenant.id, event_id="evt-1")

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].outcome == NatsEventOutcome.instantiated.value
        assert rows[0].process_instance_id == 99


class TestRecordOutcome:
    def test_updates_the_queued_row_in_place(self, app, tenant):
        NatsEventAuditService.record_queued(
            tenant_id=tenant.id, event_id="evt-1", process_identifier="group/proc"
        )

        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id,
            event_id="evt-1",
            outcome=NatsEventOutcome.instantiated.value,
            process_instance_id=4242,
            stream_seq=9_223_372_036_854_775_000,
        )

        rows = _rows()
        assert len(rows) == 1, "should update the queued row, not add a second one"
        assert rows[0].outcome == NatsEventOutcome.instantiated.value
        assert rows[0].process_instance_id == 4242
        assert rows[0].stream_seq == 9_223_372_036_854_775_000
        assert rows[0].completed_at_in_seconds is not None
        # Fields set at queue time survive the update.
        assert rows[0].process_identifier == "group/proc"

    def test_inserts_when_there_is_no_queued_row(self, app, tenant):
        """publisher.py publishes straight to NATS, so those events never get a
        queued row from the backend."""
        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id,
            event_id="evt-direct",
            outcome=NatsEventOutcome.rejected_auth.value,
            error_message="invalid api_key",
        )

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].outcome == NatsEventOutcome.rejected_auth.value
        assert rows[0].error_message == "invalid api_key"
        assert rows[0].is_failure()

    def test_records_an_unattributable_message_with_a_null_tenant(self, app):
        """A malformed subject cannot be attributed to any tenant, and that is exactly
        the failure that is invisible without this table."""
        NatsEventAuditService.record_outcome(
            tenant_id=None,
            event_id=None,
            outcome=NatsEventOutcome.invalid_payload.value,
            error_message="could not parse message body",
        )

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].tenant_id is None
        # A tenant-scoped query must never surface it.
        assert NatsEventAuditModel.query.filter_by(tenant_id="tenant-1").count() == 0

    def test_two_unattributable_messages_both_get_rows(self, app):
        """With no event id there is nothing to correlate on, so each gets its own row
        rather than silently collapsing into one."""
        for _ in range(2):
            NatsEventAuditService.record_outcome(
                tenant_id=None, event_id=None, outcome=NatsEventOutcome.invalid_payload.value
            )

        assert len(_rows()) == 2

    def test_truncates_a_long_error_message(self, app, tenant):
        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id,
            event_id="evt-1",
            outcome=NatsEventOutcome.transient_error.value,
            error_message="x" * (MAX_ERROR_MESSAGE_LENGTH * 2),
        )

        stored = _rows()[0].error_message
        assert len(stored) == MAX_ERROR_MESSAGE_LENGTH
        assert stored.endswith("...")


class TestRecordDuplicate:
    def test_counts_on_the_original_row_without_touching_its_outcome(self, app, tenant):
        """The duplicate carries the same event id as the run that succeeded, so the
        outcome must survive and only the counter moves."""
        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id,
            event_id="evt-1",
            outcome=NatsEventOutcome.instantiated.value,
            process_instance_id=7,
        )

        NatsEventAuditService.record_duplicate(tenant_id=tenant.id, event_id="evt-1")

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].outcome == NatsEventOutcome.instantiated.value
        assert rows[0].process_instance_id == 7
        assert rows[0].duplicate_count == 1

    def test_a_retry_loop_increments_rather_than_adding_rows(self, app, tenant):
        """A client stuck re-sending the same trigger must not grow the table."""
        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id, event_id="evt-1", outcome=NatsEventOutcome.instantiated.value
        )

        for _ in range(5):
            NatsEventAuditService.record_duplicate(tenant_id=tenant.id, event_id="evt-1")

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].duplicate_count == 5

    def test_bumping_the_count_moves_the_updated_timestamp(self, app, tenant):
        """This is what makes 'last duplicated at' answerable without another column."""
        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id, event_id="evt-1", outcome=NatsEventOutcome.instantiated.value
        )
        # Backdated with raw SQL on purpose: writing it through the ORM would be stamped
        # by the timestamp listener, which is the very thing under test.
        db.session.execute(
            text("UPDATE m8flow_nats_event_audit SET updated_at_in_seconds = :ts WHERE id = :id"),
            {"ts": 1000, "id": _rows()[0].id},
        )
        db.session.commit()
        db.session.expire_all()

        NatsEventAuditService.record_duplicate(tenant_id=tenant.id, event_id="evt-1")

        assert _rows()[0].updated_at_in_seconds > 1000

    def test_writes_a_duplicate_row_when_the_original_is_gone(self, app, tenant):
        """Pruned, or published straight to NATS by publisher.py so it never had a
        queued row — a suppressed delivery is all we know about it."""
        NatsEventAuditService.record_duplicate(tenant_id=tenant.id, event_id="evt-unknown")

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].outcome == NatsEventOutcome.duplicate.value
        assert rows[0].duplicate_count == 1

    def test_a_fresh_row_starts_at_zero_duplicates(self, app, tenant):
        NatsEventAuditService.record_queued(tenant_id=tenant.id, event_id="evt-1")

        assert _rows()[0].duplicate_count == 0

    def test_swallows_database_errors(self, app, tenant, monkeypatch):
        def boom():
            raise RuntimeError("database is on fire")

        monkeypatch.setattr(db.session, "commit", boom)

        NatsEventAuditService.record_duplicate(tenant_id=tenant.id, event_id="evt-1")


class TestNeverBreaksTheCaller:
    """Rule 1: recording what happened must not change what happens."""

    def test_record_outcome_swallows_database_errors(self, app, tenant, monkeypatch):
        def boom():
            raise RuntimeError("database is on fire")

        monkeypatch.setattr(db.session, "commit", boom)

        # Must not raise.
        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id, event_id="evt-1", outcome=NatsEventOutcome.instantiated.value
        )

    def test_record_queued_swallows_database_errors(self, app, tenant, monkeypatch):
        def boom():
            raise RuntimeError("database is on fire")

        monkeypatch.setattr(db.session, "commit", boom)

        NatsEventAuditService.record_queued(tenant_id=tenant.id, event_id="evt-1")

    def test_an_unwritable_audit_row_does_not_take_the_callers_work_with_it(self, app, tenant):
        """commit=False joins the caller's transaction inside a SAVEPOINT, so a row that
        violates the tenant foreign key rolls back alone and the caller still commits."""
        other = M8flowTenantModel(
            id="tenant-2",
            name="Tenant Two",
            slug="tenant-two",
            status=TenantStatus.ACTIVE,
            created_by="admin",
            modified_by="admin",
        )
        db.session.add(other)

        NatsEventAuditService.record_outcome(
            tenant_id="tenant-does-not-exist",
            event_id="evt-bad",
            outcome=NatsEventOutcome.instantiated.value,
            commit=False,
        )

        db.session.commit()

        # The caller's own work survived.
        assert M8flowTenantModel.query.filter_by(id="tenant-2").one_or_none() is not None


class TestCommitFalseJoinsTheCallerTransaction:
    def test_row_is_visible_only_after_the_caller_commits(self, app, tenant):
        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id,
            event_id="evt-1",
            outcome=NatsEventOutcome.instantiated.value,
            process_instance_id=11,
            commit=False,
        )
        db.session.commit()

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].process_instance_id == 11

    def test_caller_rollback_discards_the_audit_row(self, app, tenant):
        """The success path relies on this: no instance means no row claiming one."""
        NatsEventAuditService.record_outcome(
            tenant_id=tenant.id,
            event_id="evt-1",
            outcome=NatsEventOutcome.instantiated.value,
            commit=False,
        )
        db.session.rollback()

        assert _rows() == []


class TestPrune:
    def _terminal_row(self, tenant_id, event_id, completed_at):
        row = NatsEventAuditModel(
            tenant_id=tenant_id,
            event_id=event_id,
            worker=NatsEventWorker.consumer.value,
            outcome=NatsEventOutcome.instantiated.value,
            completed_at_in_seconds=completed_at,
        )
        db.session.add(row)
        db.session.commit()
        return row

    def test_removes_rows_past_the_retention_window(self, app, tenant):
        now = int(time.time())
        self._terminal_row(tenant.id, "old", now - (100 * SECONDS_PER_DAY))
        self._terminal_row(tenant.id, "recent", now - (10 * SECONDS_PER_DAY))

        deleted = NatsEventAuditService.prune(retention_days=90)

        assert deleted == 1
        assert [r.event_id for r in _rows()] == ["recent"]

    def test_never_prunes_an_in_flight_row(self, app, tenant):
        """A queued row has no completion time and may still be behind a backlogged
        consumer; deleting it would make the backlog count wrong."""
        NatsEventAuditService.record_queued(tenant_id=tenant.id, event_id="still-queued")

        deleted = NatsEventAuditService.prune(retention_days=1)

        assert deleted == 0
        assert len(_rows()) == 1

    def test_zero_retention_disables_pruning(self, app, tenant):
        self._terminal_row(tenant.id, "ancient", 0)

        assert NatsEventAuditService.prune(retention_days=0) == 0
        assert len(_rows()) == 1
