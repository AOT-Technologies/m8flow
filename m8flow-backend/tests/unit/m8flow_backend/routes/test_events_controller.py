"""POST /m8flow/events/m8flow-trigger publishes the key's id, never the raw key (M8F-574)."""

from __future__ import annotations

from m8flow_backend.identity import ensure_tenant
from m8flow_backend.services.nats_service import NatsService
from m8flow_backend.services.nats_token_service import NatsTokenService


def test_the_trigger_publishes_the_key_id_not_the_raw_key(app, client, db_session, monkeypatch):
    ensure_tenant(db_session, tenant_id="t-acme", slug="acme")
    db_session.commit()
    with app.test_request_context("/"):
        key, raw_key = NatsTokenService.create_named_key(tenant_id="t-acme", user_id="admin", label="k")
        key_id = key.id
    published = {}

    def _publish_event(**kwargs):
        published.update(kwargs)
        return {
            "id": "e1",
            "subject": "m8flow.events.acme.trigger",
            "tenant_id": "t-acme",
            "tenant_slug": "acme",
            "process_identifier": kwargs["process_identifier"],
            "api_key_id": kwargs["authenticated"].key_id,
            "payload": kwargs["payload"],
            "reply_to": "_INBOX.m8flow.e1",
            "signature": "sig",
            "process_instance": {"id": 7},
        }

    monkeypatch.setattr(NatsService, "publish_event", staticmethod(_publish_event))

    response = client.post(
        "/v1.0/m8flow/events/m8flow-trigger",
        json={"processIdentifier": "group-a/flow-a", "data": {"amount": 1}},
        headers={"X-M8FLOW-NATS-API-Key": raw_key},
    )

    assert response.status_code == 200, response.get_json()
    # Identity travels only as the authenticated key; there is no caller-chosen username.
    assert (published["authenticated"].key_id, published["authenticated"].created_by) == (key_id, "admin")
    assert "username" not in published
    assert raw_key not in repr(published)
    # The echo to the caller drops the internal routing and signing fields.
    event = response.get_json()["data"]["event"]
    assert not {"api_key_id", "signature", "reply_to", "tenant_id", "tenant_slug"} & event.keys()
