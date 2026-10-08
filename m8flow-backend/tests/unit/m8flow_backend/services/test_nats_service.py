"""Trigger events never carry the raw NATS API key (M8F-574)."""

from __future__ import annotations

import asyncio
import json
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
    assert NatsTokenService.verify_trigger(event)
