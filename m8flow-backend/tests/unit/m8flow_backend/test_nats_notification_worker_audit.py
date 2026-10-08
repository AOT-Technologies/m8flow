"""The notification worker's rejections must not rewrite another tenant's audit history.

A message that fails validation carries only claims: its tenant and the instance/task its
event id is built from are whatever the sender wrote.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from m8flow_backend.models.nats_event_audit import NatsEventAuditModel, NatsEventOutcome, NatsEventWorker
from m8flow_backend.services.nats_event_audit_service import NatsEventAuditService

_CONSUMER_DIR = Path(__file__).resolve().parents[4] / "m8flow-nats-consumer"


@pytest.fixture
def worker(app, monkeypatch):
    # Never read the developer's real .env into the test session.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setenv("M8FLOW_NATS_URL", "nats://unused:4222")
    monkeypatch.syspath_prepend(str(_CONSUMER_DIR))
    sys.modules.pop("notification_worker", None)
    module = importlib.import_module("notification_worker")
    monkeypatch.setattr(module, "flask_app", app)
    yield module
    sys.modules.pop("notification_worker", None)


class _Message:
    def __init__(self, subject: str, body: dict, seq: int):
        self.subject = subject
        self.data = json.dumps(body).encode()
        self.metadata = SimpleNamespace(sequence=SimpleNamespace(stream=seq))
        self.acked = False

    async def ack(self):
        self.acked = True


def test_a_rejected_message_cannot_rewrite_another_tenants_row(worker, db_session):
    NatsEventAuditService.record_outcome(
        tenant_id="t-victim",
        event_id="extform-7-task-1",
        outcome=NatsEventOutcome.transient_error.value,
        worker=NatsEventWorker.notification_worker.value,
        error_message="smtp down",
    )
    # The subject names one tenant while the payload claims the victim's instance and task.
    forged = _Message(
        "m8flow.notifications.evil.external-form",
        {
            "tenant_id": "t-victim",
            "tenant_slug": "victim",
            "process_instance_id": 7,
            "task_guid": "task-1",
            "request_ids": [1],
        },
        seq=5,
    )

    asyncio.run(worker.process_message(forged))

    db_session.expire_all()
    victim = db_session.scalars(select(NatsEventAuditModel)).one()
    assert (victim.outcome, victim.error_message) == (NatsEventOutcome.transient_error.value, "smtp down")
    assert forged.acked


def test_a_requests_created_event_notifies_each_row_id(worker, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        worker, "_notify_one", lambda tenant_id, request_id: calls.append((tenant_id, request_id)) or "sent"
    )
    msg = _Message(
        "m8flow.notifications.acme.external-form",
        {
            "tenant_id": "t1",
            "tenant_slug": "acme",
            "process_instance_id": 7,
            "task_guid": "task-1",
            "request_ids": [11, 12],
        },
        seq=1,
    )

    asyncio.run(worker.process_message(msg))

    assert calls == [("t1", 11), ("t1", 12)]
    assert msg.acked


@pytest.mark.parametrize(
    "ids",
    [
        {"reference_ids": ["a-secret-link-reference"]},
        {"request_ids": [True]},
        {"request_ids": "12"},
        {"request_ids": 12},
    ],
    ids=["legacy-reference-ids", "bool", "string", "scalar"],
)
def test_a_legacy_or_malformed_event_is_discarded_for_the_sweep(worker, db_session, monkeypatch, ids):
    """Messages published before M8F-574 carry reference ids. They, and any event without a
    list of integer row ids, are dropped unread; the sweep emails the rows after the grace
    period, so nothing is lost on a rolling deploy."""
    calls = []
    monkeypatch.setattr(worker, "_notify_one", lambda *args: calls.append(args))
    msg = _Message(
        "m8flow.notifications.acme.external-form",
        {
            "tenant_id": "t1",
            "tenant_slug": "acme",
            "process_instance_id": 8,
            "task_guid": "task-1",
            **ids,
        },
        seq=2,
    )

    asyncio.run(worker.process_message(msg))

    assert calls == []
    assert msg.acked
    db_session.expire_all()
    audit = db_session.scalars(select(NatsEventAuditModel)).one()
    assert audit.outcome == NatsEventOutcome.invalid_payload.value


def test_the_sweep_notifies_by_row_id(worker, monkeypatch):
    from m8flow_backend.services.external_form_notification_service import ExternalFormNotificationService

    calls = []
    monkeypatch.setattr(worker, "_revive_reconfigured_tenants", lambda: None)
    monkeypatch.setattr(
        ExternalFormNotificationService, "sweep_candidates", classmethod(lambda cls: [(5, "t1"), (6, "t1")])
    )
    monkeypatch.setattr(
        ExternalFormNotificationService,
        "smtp_readiness",
        classmethod(lambda cls, tenant_id=None: {"ok": True, "reason": None}),
    )
    monkeypatch.setattr(
        worker, "_notify_one", lambda tenant_id, request_id: calls.append((tenant_id, request_id)) or "sent"
    )

    worker._run_sweep()

    assert calls == [("t1", 5), ("t1", 6)]


def test_the_sweep_parks_a_tenant_without_smtp_by_row_id(worker, monkeypatch):
    from m8flow_backend.services.external_form_notification_service import ExternalFormNotificationService

    parked = []
    monkeypatch.setattr(worker, "_revive_reconfigured_tenants", lambda: None)
    monkeypatch.setattr(
        ExternalFormNotificationService, "sweep_candidates", classmethod(lambda cls: [(5, "t1"), (6, "t1")])
    )
    monkeypatch.setattr(
        ExternalFormNotificationService,
        "smtp_readiness",
        classmethod(lambda cls, tenant_id=None: {"ok": False, "reason": "no SMTP"}),
    )
    monkeypatch.setattr(
        ExternalFormNotificationService,
        "mark_smtp_unconfigured",
        classmethod(lambda cls, request_ids, reason: parked.append((request_ids, reason)) or len(request_ids)),
    )
    monkeypatch.setattr(worker, "_notify_one", lambda *_args: pytest.fail("a parked tenant must not be emailed"))

    worker._run_sweep()

    assert parked == [([5, 6], "no SMTP")]


def test_without_nats_the_worker_still_runs_the_email_sweep(worker, app, monkeypatch):
    """M8F-574 Issue V: the sweep reads only the database, so it must deliver external-form
    emails when NATS is off instead of the worker idling."""
    swept = []

    async def fake_sweep_loop():
        swept.append(True)

    monkeypatch.setitem(sys.modules, "m8flow_backend.app", SimpleNamespace(app=app))
    monkeypatch.setattr("m8flow_backend.config.nats_enabled", lambda: False)
    monkeypatch.setattr(worker, "NATS", lambda: pytest.fail("must not connect to NATS"))
    monkeypatch.setattr(worker, "sweep_loop", fake_sweep_loop)

    asyncio.run(worker.main())

    assert swept == [True]
