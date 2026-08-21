"""Seeding a "default" profile from pre-existing fixed-key Secrets.

The invariant under test is that seeding is additive: the original Secrets stay
put, so every process model that spells out ``M8FLOW_SECRET:...`` keeps working.
"""

from __future__ import annotations

import pytest

from m8flow_backend.services import connector_profile_migration as migration


@pytest.fixture
def seeded(monkeypatch):
    """Fake the secret reads and the profile writes."""
    state: dict = {"secrets": {}, "profiles": [], "created": []}

    monkeypatch.setattr(
        migration,
        "_existing_secret_values",
        lambda keys: {k: v for k, v in state["secrets"].items() if k in keys},
    )

    from m8flow_backend.services import connector_profile_service as service

    class FakeService:
        @staticmethod
        def list_profiles(connector_type=None, **_kwargs):
            return [
                profile
                for profile in state["profiles"]
                if connector_type is None
                or profile.connector_type == connector_type
            ]

        @staticmethod
        def create_profile(body, user_id):
            created = type(
                "Row",
                (),
                {
                    "connector_type": body["connector_type"],
                    "profile_name": body["profile_name"],
                    "config": body["config"],
                    "is_default": body.get("is_default"),
                },
            )()
            state["created"].append(body)
            state["profiles"].append(created)
            return created

    monkeypatch.setattr(service, "ConnectorProfileService", FakeService)
    monkeypatch.setattr(migration, "logger", migration.logger)
    return state


def _existing(connector_type: str, profile_name: str):
    return type(
        "Row", (), {"connector_type": connector_type, "profile_name": profile_name}
    )()


def test_seeds_a_default_profile_from_stored_secrets(seeded):
    seeded["secrets"] = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "mailer",
        "SMTP_PASSWORD": "pw",
    }

    result = migration.seed_default_profile("smtp", user_id=1)

    assert result is not None
    body = seeded["created"][0]
    assert body["profile_name"] == "default"
    assert body["is_default"] is True
    # Old display-oriented keys become the proxy's keyword arguments.
    assert body["config"] == {
        "smtp_host": "smtp.example.com",
        "smtp_port": "587",
        "smtp_user": "mailer",
        "smtp_password": "pw",
    }


def test_seeding_is_idempotent(seeded):
    seeded["secrets"] = {"SLACK_TOKEN": "xoxb-1"}

    assert migration.seed_default_profile("slack") is not None
    # A second run must not create a duplicate or raise.
    assert migration.seed_default_profile("slack") is None
    assert len(seeded["created"]) == 1


def test_nothing_is_seeded_when_no_secrets_were_configured(seeded):
    seeded["secrets"] = {}
    assert migration.seed_default_profile("smtp") is None
    assert seeded["created"] == []


def test_an_existing_default_profile_is_left_alone(seeded):
    seeded["secrets"] = {"SLACK_TOKEN": "xoxb-1"}
    seeded["profiles"].append(_existing("slack", "default"))

    assert migration.seed_default_profile("slack") is None
    assert seeded["created"] == []


def test_other_profiles_do_not_block_seeding(seeded):
    """Only a profile literally named "default" counts as already-seeded."""
    seeded["secrets"] = {"SLACK_TOKEN": "xoxb-1"}
    seeded["profiles"].append(_existing("slack", "team-alerts"))

    assert migration.seed_default_profile("slack") is not None


def test_a_connector_with_no_mapping_is_skipped(seeded):
    """github's proxy parameter name is unverified, so it is not seeded.

    Seeding it could store the credential under a name the connector never
    reads, which is worse than leaving it to be entered by hand.
    """
    seeded["secrets"] = {"GITHUB_PAT_TOKEN": "ghp_x"}
    assert migration.seed_default_profile("github") is None
    assert "github" not in migration.SECRET_KEY_TO_FIELD


def test_partial_credentials_seed_what_exists(seeded):
    seeded["secrets"] = {"SMTP_HOST": "h", "SMTP_PASSWORD": "pw"}

    migration.seed_default_profile("smtp")

    assert seeded["created"][0]["config"] == {
        "smtp_host": "h",
        "smtp_password": "pw",
    }


def test_a_validation_failure_does_not_raise(seeded, monkeypatch):
    """Seeding is best effort: it must never block startup or a request."""
    from m8flow_backend.services import connector_profile_service as service

    seeded["secrets"] = {"SMTP_HOST": "h"}

    def boom(body, user_id):
        raise service.ConnectorProfileError("missing password", status_code=400)

    monkeypatch.setattr(service.ConnectorProfileService, "create_profile", boom)

    assert migration.seed_default_profile("smtp") is None


def test_seed_all_reports_what_it_created(seeded):
    seeded["secrets"] = {
        "SMTP_HOST": "h",
        "SMTP_PASSWORD": "pw",
        "SLACK_TOKEN": "xoxb-1",
    }

    created = migration.seed_all_default_profiles()

    assert set(created) == {"smtp", "slack"}


def test_every_mapped_field_exists_on_its_definition():
    """A typo in the mapping would store a value nothing ever reads."""
    from m8flow_backend.connectors.registry import get_connector

    for connector_type, mapping in migration.SECRET_KEY_TO_FIELD.items():
        definition = get_connector(connector_type)
        assert definition is not None, connector_type
        profile_fields = set(definition.profile_field_names())
        for secret_key, field_name in mapping.items():
            assert field_name in profile_fields, f"{connector_type}.{field_name}"


def test_mapped_values_pass_phase_one_validation():
    """The seeded config must actually be savable.

    Secrets come back as strings, so this is what catches a mapping onto a typed
    field (smtp_port is Literal[25, 587, 465]) that string input would reject.
    """
    from m8flow_backend.connectors.registry import get_connector
    from m8flow_backend.connectors.validation import validate_profile

    sample = {
        "smtp": {
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_user": "u",
            "smtp_password": "p",
            "email_from": "from@example.com",
        },
        "slack": {"token": "xoxb-1", "channel": "#general"},
        "postgres_v2": {"database_connection_str": "dbname=x"},
        "stripe": {"api_key": "sk_test_1"},
        "salesforce": {
            "client_id": "c",
            "client_secret": "s",
            "access_token": "a",
            "refresh_token": "r",
            "instance_url": "https://x.my.salesforce.com",
        },
    }

    for connector_type, values in sample.items():
        _, errors = validate_profile(get_connector(connector_type), values)
        assert errors == [], f"{connector_type}: {errors}"
