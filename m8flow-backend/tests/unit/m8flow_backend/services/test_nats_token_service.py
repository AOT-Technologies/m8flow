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
        assert key.created_at_in_seconds > 0
        assert [k.id for k in NatsTokenService.list_keys("m8flow")] == [key.id]
        assert NatsTokenService.list_keys("other-tenant") == []

        auth = NatsTokenService.authenticate_key(raw)
        assert auth is not None
        assert (auth.tenant_id, auth.key_id, auth.scope) == ("m8flow", key.id, "group-a/flow-a")
        assert NatsTokenService.authenticate_key(raw + "x") is None

        assert NatsTokenService.revoke_key("m8flow", key.id, "editor") is True
        assert NatsTokenService.authenticate_key(raw) is None
