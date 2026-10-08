"""Trigger events never carry the raw NATS API key (M8F-574)."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from m8flow_backend.services import nats_service
from m8flow_backend.services.nats_token_service import NatsTokenService


class _Subscription:
    async def unsubscribe(self):
        pass


class _FakeNats:
    def __init__(self):
        self.sent = []

    async def connect(self, *_args, **_kwargs):
        pass

    def jetstream(self):
        sent = self.sent

        class _JetStream:
            async def publish(self, _subject, body, headers=None):
                sent.append(json.loads(body))
                return SimpleNamespace(stream="M8FLOW_EVENTS", seq=1)

        return _JetStream()

    async def subscribe(self, *_args, **_kwargs):
        return _Subscription()

    async def close(self):
        pass


def test_a_trigger_event_carries_a_signed_key_id_never_the_raw_key(monkeypatch):
    fake = _FakeNats()
    monkeypatch.setattr(nats_service, "NATS", lambda: fake)
    monkeypatch.setattr(nats_service, "nats_url", lambda: "nats://nats:4222")

    asyncio.run(
        nats_service.NatsService._publish(
            tenant_id="t1",
            tenant_slug="acme",
            process_identifier="g/p",
            payload={"amount": 1},
            api_key_id="abc123",
            reply_timeout=0.01,
        )
    )

    [event] = fake.sent
    assert "api_key" not in event and "username" not in event
    assert event["api_key_id"] == "abc123"
    assert abs(event["issued_at"] - int(time.time())) <= 5
    assert NatsTokenService.verify_trigger(event)


def test_publish_event_takes_tenant_owner_and_key_from_the_authenticated_key(app, db_session, monkeypatch):
    """The caller cannot name who owns the process: everything identity-related comes from
    the key the route authenticated (M8F-574 review)."""
    from sqlalchemy import select

    from m8flow_backend.models.nats_event_audit import NatsEventAuditModel
    from m8flow_backend.services.nats_token_service import AuthenticatedKey

    sent = {}

    async def fake_publish(**kwargs):
        sent.update(kwargs)
        return {"id": kwargs["event_id"], "process_instance": None}

    monkeypatch.setattr(nats_service.NatsService, "_publish", staticmethod(fake_publish))
    key = AuthenticatedKey(tenant_id="t1", key_id="abc123", created_by="owner", scope=None)

    with app.app_context():
        nats_service.NatsService.publish_event(
            authenticated=key, tenant_slug="acme", process_identifier="g/p", payload={}
        )

    assert (sent["tenant_id"], sent["api_key_id"]) == ("t1", "abc123")
    db_session.expire_all()
    assert db_session.scalars(select(NatsEventAuditModel)).one().username == "owner"
