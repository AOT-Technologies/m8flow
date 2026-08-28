"""Profile config and secret write semantics.

The invariant under test is "blank means unchanged": a secret value is
write-only, so an edit form cannot echo the stored one back. If an empty input
were taken at face value, every edit of an unrelated field would silently
destroy credentials the user never touched.

``_update_config`` takes the profile row as an argument and only reads plain
attributes off it, so these drive it with a stub row and a fake secret backend
-- no database, no fixtures.
"""

from __future__ import annotations

import pytest

from m8flow_backend.connectors.base import secret_ref
from m8flow_backend.connectors.registry import get_connector
from m8flow_backend.services import connector_secret_backend
from m8flow_backend.services.connector_profile_service import (
    ConnectorProfileError,
    ConnectorProfileService,
)


class _FakeBackend:
    """Records writes and deletes instead of touching the secret store."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.upserts: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.delete_error: Exception | None = None

    def create(self, key: str, value: str, user_id: int | None) -> None:
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def upsert(self, key: str, value: str, user_id: int | None) -> None:
        self.values[key] = value
        self.upserts.append((key, value))

    def delete(self, key: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.values.pop(key, None)
        self.deleted.append(key)


class _StubProfile:
    """The handful of row attributes _update_config reads and writes."""

    def __init__(self, **kwargs) -> None:
        self.id = kwargs.get("id", 42)
        self.connector_type = kwargs.get("connector_type", "smtp")
        self.config_json = kwargs.get("config_json", {})
        self.secret_refs = kwargs.get("secret_refs", {})
        self.is_active = kwargs.get("is_active", True)


@pytest.fixture
def backend():
    """Install a fake secret backend, then put the real one back."""
    original = connector_secret_backend.secret_backend()
    fake = _FakeBackend()
    connector_secret_backend.set_secret_backend(fake)
    yield fake
    connector_secret_backend.set_secret_backend(original)


@pytest.fixture
def smtp():
    return get_connector("smtp")


@pytest.fixture
def slack():
    """A connector whose secret is *required* at phase 1.

    SMTP has no required secret, so it cannot exercise the stored-secret
    placeholder at all; slack's ``token`` can.
    """
    return get_connector("slack")


@pytest.fixture
def slack_stored(backend):
    """A saved slack profile: required token in the store, channel on the row."""
    profile = _StubProfile(
        connector_type="slack",
        config_json={"channel": "#general"},
        secret_refs={"token": secret_ref(42, "token")},
    )
    backend.values[profile.secret_refs["token"]] = "xoxb-original"
    return profile


@pytest.fixture
def stored(backend, smtp):
    """A profile with both secrets already written, as an edit would find it."""
    profile = _StubProfile(
        config_json={"smtp_host": "smtp.example.com", "smtp_port": 587},
        secret_refs={
            "smtp_user": secret_ref(42, "smtp_user"),
            "smtp_password": secret_ref(42, "smtp_password"),
        },
    )
    for name, key in profile.secret_refs.items():
        backend.values[key] = f"original-{name}"
    return profile


def _update(profile, definition, config, user_id=7):
    ConnectorProfileService._update_config(profile, definition, config, user_id)


# --------------------------------------------------------- blank means unchanged


def test_blank_secret_does_not_erase_the_stored_reference(stored, smtp, backend):
    """The whole point: an empty password field keeps the stored password."""
    original_refs = dict(stored.secret_refs)

    _update(stored, smtp, {"smtp_host": "smtp.example.com", "smtp_password": ""})

    assert stored.secret_refs == original_refs
    assert backend.values[original_refs["smtp_password"]] == "original-smtp_password"
    assert backend.upserts == []


def test_none_secret_does_not_erase_the_stored_reference(stored, smtp, backend):
    _update(stored, smtp, {"smtp_host": "smtp.example.com", "smtp_password": None})

    assert backend.values[stored.secret_refs["smtp_password"]] == "original-smtp_password"
    assert backend.upserts == []


def test_secret_omitted_entirely_is_left_alone(stored, smtp, backend):
    """Editing only a non-secret field must not disturb the credentials."""
    _update(stored, smtp, {"smtp_host": "relay.example.com"})

    assert stored.config_json["smtp_host"] == "relay.example.com"
    assert backend.values[stored.secret_refs["smtp_password"]] == "original-smtp_password"
    assert backend.upserts == []


# ------------------------------------------------------- stored secrets validate


def test_stored_required_secret_is_not_reported_missing(slack_stored, slack):
    """A required secret already in the store must satisfy validation.

    Slack's token is required at phase 1. Without the placeholder the service
    seeds for each stored ref, editing the channel alone would fail with
    "token is required" against a profile that plainly has one.
    """
    _update(slack_stored, slack, {"channel": "#alerts"})

    assert slack_stored.config_json["channel"] == "#alerts"
    assert slack_stored.secret_refs["token"] == secret_ref(42, "token")


def test_blank_required_secret_still_validates_against_the_stored_one(
    slack_stored, slack, backend
):
    """Submitting the edit form with the token box left empty must not fail."""
    _update(slack_stored, slack, {"channel": "#alerts", "token": ""})

    assert slack_stored.config_json["channel"] == "#alerts"
    assert backend.values[secret_ref(42, "token")] == "xoxb-original"
    assert backend.upserts == []


def test_placeholder_never_reaches_config_json(slack_stored, slack):
    """The 'unchanged' sentinel exists only to satisfy validation."""
    _update(slack_stored, slack, {"channel": "#alerts"})

    assert "unchanged" not in slack_stored.config_json.values()
    assert "token" not in slack_stored.config_json


def test_secret_values_are_never_stored_on_the_row(stored, smtp):
    _update(stored, smtp, {"smtp_host": "relay.example.com", "smtp_password": "hunter2"})

    assert "hunter2" not in stored.config_json.values()
    assert "smtp_password" not in stored.config_json


# ------------------------------------------------------------- supplying secrets


def test_supplied_secret_upserts_against_the_existing_reference(stored, smtp, backend):
    """The ref is keyed on the immutable row id, so an update reuses it.

    A freshly minted key would leave the old secret orphaned and live.
    """
    existing = stored.secret_refs["smtp_password"]

    _update(stored, smtp, {"smtp_host": "smtp.example.com", "smtp_password": "new-pw"})

    assert stored.secret_refs["smtp_password"] == existing
    assert backend.upserts == [(existing, "new-pw")]
    assert backend.values[existing] == "new-pw"


def test_first_value_for_a_secret_mints_a_reference(backend, smtp):
    """A profile saved without an optional secret can gain one later."""
    profile = _StubProfile(
        config_json={"smtp_host": "smtp.example.com", "smtp_port": 587},
        secret_refs={"smtp_password": secret_ref(42, "smtp_password")},
    )
    backend.values[profile.secret_refs["smtp_password"]] = "pw"

    _update(profile, smtp, {"smtp_host": "smtp.example.com", "smtp_user": "bob"})

    assert profile.secret_refs["smtp_user"] == secret_ref(42, "smtp_user")
    assert backend.values[secret_ref(42, "smtp_user")] == "bob"


# ------------------------------------------------------------------ config merge


def test_non_secret_fields_merge_over_stored_config(backend, smtp):
    """A patch touching one field must not drop a stored field it omits.

    email_from is absent from the patch and has no default, so it survives only
    if the stored config is merged rather than replaced.
    """
    profile = _StubProfile(
        config_json={
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "email_from": "noreply@example.com",
        },
        secret_refs={},
    )

    _update(profile, smtp, {"smtp_host": "relay.example.com"})

    assert profile.config_json["smtp_host"] == "relay.example.com"
    assert profile.config_json["email_from"] == "noreply@example.com"
    assert profile.config_json["smtp_port"] == 465


def test_invalid_value_raises_before_any_secret_is_written(stored, smtp, backend):
    with pytest.raises(ConnectorProfileError) as caught:
        _update(
            stored,
            smtp,
            {"smtp_host": "relay.example.com", "smtp_port": 9999, "smtp_password": "pw"},
        )

    assert caught.value.status_code == 400
    assert caught.value.errors
    assert backend.upserts == []
    assert stored.config_json["smtp_host"] == "smtp.example.com"


# ------------------------------------------------------- deactivate and delete


@pytest.fixture
def no_commit(monkeypatch):
    """Neutralize the session writes so these stay pure-unit tests.

    ``deactivate_profile`` and ``delete_profile`` both end in
    ``db.session.commit()``, which raises "Working outside of application
    context" before the assertions are reached. This module deliberately runs
    with no database, so standing up a real session would be the wrong fix --
    what is under test is which flags the service sets and the order it
    removes things in.
    """
    from unittest.mock import MagicMock
    from spiffworkflow_backend.models.db import db

    mock_session = MagicMock()
    monkeypatch.setattr(db, "session", mock_session)


def test_deactivate_is_a_soft_delete(monkeypatch, backend, no_commit):
    """Deactivating clears is_active but leaves the row and its secrets in
    place, so the profile stays recoverable."""
    profile = _StubProfile(is_active=True)
    monkeypatch.setattr(
        ConnectorProfileService, "get_profile", classmethod(lambda cls, _id: profile)
    )

    ConnectorProfileService.deactivate_profile(profile.id)

    assert profile.is_active is False


def test_delete_removes_the_row_before_the_secrets(monkeypatch, backend, no_commit):
    """Row first, so a failure orphans unreachable secrets rather than the reverse."""
    order: list[str] = []
    profile = _StubProfile(
        secret_refs={"smtp_password": secret_ref(42, "smtp_password")}
    )
    backend.values[secret_ref(42, "smtp_password")] = "pw"
    monkeypatch.setattr(
        ConnectorProfileService, "get_profile", classmethod(lambda cls, _id: profile)
    )

    from spiffworkflow_backend.models.db import db

    monkeypatch.setattr(
        db.session, "delete", lambda _row: order.append("row"), raising=False
    )
    original_delete = backend.delete

    def tracking_delete(key):
        order.append("secret")
        original_delete(key)

    monkeypatch.setattr(backend, "delete", tracking_delete)

    ConnectorProfileService.delete_profile(profile.id)

    assert order == ["row", "secret"]
    assert backend.deleted == [secret_ref(42, "smtp_password")]


def test_delete_survives_a_failing_secret_removal(monkeypatch, backend, no_commit):
    """Secret cleanup is best effort: the row is already gone."""
    profile = _StubProfile(
        secret_refs={
            "smtp_user": secret_ref(42, "smtp_user"),
            "smtp_password": secret_ref(42, "smtp_password"),
        }
    )
    monkeypatch.setattr(
        ConnectorProfileService, "get_profile", classmethod(lambda cls, _id: profile)
    )
    backend.delete_error = RuntimeError("secret store unavailable")

    ConnectorProfileService.delete_profile(profile.id)  # must not raise


def test_delete_reports_how_many_secrets_were_left_behind(monkeypatch, backend, caplog, no_commit):
    """Ops need the orphan count to size a cleanup; key names stay out of the log."""
    ref = secret_ref(42, "smtp_password")
    profile = _StubProfile(secret_refs={"smtp_password": ref})
    monkeypatch.setattr(
        ConnectorProfileService, "get_profile", classmethod(lambda cls, _id: profile)
    )
    backend.delete_error = RuntimeError("secret store unavailable")

    with caplog.at_level("WARNING"):
        ConnectorProfileService.delete_profile(profile.id)

    summary = [r for r in caplog.records if "undeleted" in r.getMessage()]
    assert len(summary) == 1
    assert "1 of 1" in summary[0].getMessage()
    assert ref not in summary[0].getMessage()


def test_delete_logs_no_summary_when_every_secret_goes(monkeypatch, backend, caplog, no_commit):
    profile = _StubProfile(secret_refs={"smtp_password": secret_ref(42, "smtp_password")})
    monkeypatch.setattr(
        ConnectorProfileService, "get_profile", classmethod(lambda cls, _id: profile)
    )

    with caplog.at_level("WARNING"):
        ConnectorProfileService.delete_profile(profile.id)

    assert not [r for r in caplog.records if "undeleted" in r.getMessage()]
