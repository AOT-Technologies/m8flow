"""NatsTokenService against the real ORM schema.

Regression: the model on this branch was a placeholder (``key_hash``/``name``), so
creating a key raised "'label' is an invalid keyword argument" and every
POST /m8flow/nats-tokens returned 500.
"""

from __future__ import annotations

import pytest

from m8flow_backend.config import nats_trigger_max_age_seconds
from m8flow_backend.errors import ApiError
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
        "issued_at": 1_800_000_000,
    }
    event["signature"] = NatsTokenService.sign_trigger(event)

    assert NatsTokenService.verify_trigger(event)
    assert NatsTokenService.verify_trigger({**event, "username": "anyone"})  # unsigned extras are ignored
    assert not NatsTokenService.verify_trigger({**event, "api_key_id": "k2"})
    assert not NatsTokenService.verify_trigger({**event, "payload": {"amount": 2}})
    assert not NatsTokenService.verify_trigger({**event, "issued_at": 1_800_000_001})  # no re-dating a replay
    assert not NatsTokenService.verify_trigger({**event, "signature": "é"})
    assert not NatsTokenService.verify_trigger({k: v for k, v in event.items() if k != "signature"})


@pytest.mark.parametrize(
    "salt", [None, "m8flow_default_salt", "changeme_nats_salt", "my-random-salt-string", "x" * 31]
)
def test_a_public_salt_neither_signs_nor_verifies_a_trigger(monkeypatch, salt):
    """M8F-574 review: the signature is the consumer's only proof a trigger came from the
    backend. With the salt unset, a value published in this repo, or short enough to
    brute-force from a signed event read off the broker, anyone who can publish to the
    broker could sign an event naming any key, so triggers fail closed."""
    if salt is None:
        monkeypatch.delenv("M8FLOW_NATS_TOKEN_SALT", raising=False)
    else:
        monkeypatch.setenv("M8FLOW_NATS_TOKEN_SALT", salt)
    event = {"id": "e1", "tenant_id": "t1", "api_key_id": "victims-key", "issued_at": 1_800_000_000}

    with pytest.raises(ApiError) as refused:
        NatsTokenService.sign_trigger(event)
    assert refused.value.status_code == 503

    # Signed exactly as the backend would with the public value.
    forged = {**event, "signature": NatsTokenService._trigger_signature(event, salt or "m8flow_default_salt")}
    assert not NatsTokenService.verify_trigger(forged)


def test_a_trigger_is_fresh_only_inside_the_window(monkeypatch):
    """A signature proves who issued an event, not when; the window bounds how long a
    captured event can be replayed (M8F-574 review)."""
    monkeypatch.setenv("M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS", "300")
    now = 1_800_000_000
    fresh = NatsTokenService.trigger_is_fresh

    assert fresh({"issued_at": now - 300}, now=now)
    assert fresh({"issued_at": now + 300}, now=now)  # clock skew between hosts, either way
    assert not fresh({"issued_at": now - 301}, now=now)  # a replay of a captured event
    assert not fresh({"issued_at": now + 301}, now=now)
    assert not fresh({}, now=now)
    assert not fresh({"issued_at": str(now)}, now=now)
    assert not fresh({"issued_at": True}, now=now)


@pytest.mark.parametrize("raw", ["abc", "-1", "0", "1.5"])
def test_a_bad_trigger_max_age_is_a_config_error(monkeypatch, raw):
    """M8F-574 review: a negative window would refuse every trigger and a non-number would
    fail each message, so either is reported as a config error naming the variable."""
    monkeypatch.setenv("M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS", raw)

    with pytest.raises(ValueError, match="M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS"):
        nats_trigger_max_age_seconds()


@pytest.mark.parametrize("raw", [" ", " 300 ", "300 ", "\t300\n"])
def test_a_blank_or_padded_trigger_max_age_still_parses(monkeypatch, raw):
    """M8F-574 review: env files often pad values, and the consumer will not start on a bad
    one. config._get strips before validating; blank means unset, so the default."""
    monkeypatch.setenv("M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS", raw)

    assert nats_trigger_max_age_seconds() == 300


def test_a_trigger_signature_ignores_key_order_at_every_level():
    """M8F-574 review: the payload is signed canonically. json.dumps(sort_keys=True) sorts
    nested objects too, including ones inside lists, so a payload whose keys come back in
    another order (after the broker round trip, or from another producer) still verifies."""
    event = {
        "id": "e1",
        "tenant_id": "t1",
        "api_key_id": "k1",
        "issued_at": 1_800_000_000,
        "payload": {"b": 1, "a": {"z": 1, "y": [{"d": 1, "c": 2}, 3]}},
    }
    event["signature"] = NatsTokenService.sign_trigger(event)
    shuffled = {
        "payload": {"a": {"y": [{"c": 2, "d": 1}, 3], "z": 1}, "b": 1},
        "issued_at": 1_800_000_000,
        "api_key_id": "k1",
        "tenant_id": "t1",
        "id": "e1",
        "signature": event["signature"],
    }

    assert NatsTokenService.verify_trigger(shuffled)
    # Key order is ignored; array order is content, so reordering a list breaks it.
    assert not NatsTokenService.verify_trigger(
        {**shuffled, "payload": {"a": {"y": [3, {"c": 2, "d": 1}], "z": 1}, "b": 1}}
    )
