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
            "reference_ids": ["r1"],
        },
        seq=5,
    )

    asyncio.run(worker.process_message(forged))

    db_session.expire_all()
    victim = db_session.scalars(select(NatsEventAuditModel)).one()
    assert (victim.outcome, victim.error_message) == (NatsEventOutcome.transient_error.value, "smtp down")
    assert forged.acked


@pytest.mark.parametrize("not_sent", ["failed:Connection timed out", "skipped:smtp_unconfigured"])
def test_an_email_that_was_not_sent_is_audited_as_a_failure(worker, db_session, monkeypatch, not_sent):
    """M8F-575 issue 4: notify() reports an unsent email as a result string instead of
    raising, so the event was audited as "Sent" and NATS tenant counts hid email failures."""
    results = {"ref-ok-1": "sent", "ref-bad-2": not_sent}
    monkeypatch.setattr(worker, "_notify_one", lambda _tenant_id, reference_id: results[reference_id])
    msg = _Message(
        "m8flow.notifications.acme.external-form",
        {
            "tenant_id": "t1",
            "tenant_slug": "acme",
            "process_instance_id": 7,
            "task_guid": "task-1",
            "reference_ids": ["ref-ok-1", "ref-bad-2"],
        },
        seq=3,
    )

    asyncio.run(worker.process_message(msg))

    db_session.expire_all()
    row = db_session.scalars(select(NatsEventAuditModel)).one()
    assert row.outcome == NatsEventOutcome.transient_error.value
    assert not_sent in row.error_message
    assert "ref-ok-1"[:8] not in row.error_message


def test_a_sent_email_is_audited_as_sent(worker, db_session, monkeypatch):
    monkeypatch.setattr(worker, "_notify_one", lambda *_args: "sent")
    msg = _Message(
        "m8flow.notifications.acme.external-form",
        {"tenant_id": "t1", "tenant_slug": "acme", "process_instance_id": 8, "task_guid": "t", "reference_ids": ["r"]},
        seq=4,
    )

    asyncio.run(worker.process_message(msg))

    db_session.expire_all()
    assert db_session.scalars(select(NatsEventAuditModel)).one().outcome == NatsEventOutcome.instantiated.value
