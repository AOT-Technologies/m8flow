"""NatsTokenService against the real ORM schema.

Regression: the model on this branch was a placeholder (``key_hash``/``name``), so
creating a key raised "'label' is an invalid keyword argument" and every
POST /m8flow/nats-tokens returned 500.
"""

from __future__ import annotations

from m8flow_backend.services.nats_token_service import NatsTokenService


def test_create_list_authenticate_revoke_round_trip(app):
    with app.test_request_context("/v1.0/m8flow/nats-tokens"):
        key, raw = NatsTokenService.create_named_key(
            tenant_id="m8flow",
            user_id="editor",
            label="my-integration-key",
            expires_in_seconds=30 * 24 * 60 * 60,
            scope="group-a/flow-a",
        )

        assert raw.startswith(f"m8f_{key.id}.")
        assert key.label == "my-integration-key"
        assert key.created_at is not None
        assert key.updated_at is not None
        assert [k.id for k in NatsTokenService.list_keys("m8flow")] == [key.id]
        assert NatsTokenService.list_keys("other-tenant") == []

        auth = NatsTokenService.authenticate_key(raw)
        assert auth is not None
        assert (auth.tenant_id, auth.key_id, auth.scope) == ("m8flow", key.id, "group-a/flow-a")
        assert NatsTokenService.authenticate_key(raw + "x") is None

        assert NatsTokenService.revoke_key("m8flow", key.id, "editor") is True
        assert NatsTokenService.authenticate_key(raw) is None


def test_resolve_key_id_names_the_owner_until_the_key_is_revoked(app):
    with app.test_request_context("/v1.0/m8flow/nats-tokens"):
        key, _raw = NatsTokenService.create_named_key(tenant_id="m8flow", user_id="editor", label="k")

        assert NatsTokenService.resolve_key_id(key.id).created_by == "editor"
        assert NatsTokenService.resolve_key_id("no-such-key") is None

        NatsTokenService.revoke_key("m8flow", key.id, "editor")
        assert NatsTokenService.resolve_key_id(key.id) is None


def test_a_signed_trigger_verifies_and_any_signed_change_breaks_it():
    event = {
        "id": "e1",
        "tenant_id": "t1",
        "tenant_slug": "acme",
        "process_identifier": "g/p",
        "api_key_id": "k1",
        "payload": {"amount": 1},
        "reply_to": None,
    }
    event["signature"] = NatsTokenService.sign_trigger(event)

    assert NatsTokenService.verify_trigger(event)
    assert NatsTokenService.verify_trigger({**event, "username": "anyone"})  # unsigned extras are ignored
    assert not NatsTokenService.verify_trigger({**event, "api_key_id": "k2"})
    assert not NatsTokenService.verify_trigger({**event, "payload": {"amount": 2}})
    assert not NatsTokenService.verify_trigger({**event, "signature": "é"})
    assert not NatsTokenService.verify_trigger({k: v for k, v in event.items() if k != "signature"})
