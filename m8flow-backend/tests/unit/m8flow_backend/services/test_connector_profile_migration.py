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
    state: dict = {"secrets": {}, "profiles": [], "created": [], "audits": []}

    # Capture audit events instead of writing them: these tests run with no app
    # context, and the point is to assert on what gets recorded.
    monkeypatch.setattr(
        migration,
        "_audit",
        lambda event_type, status, message, **kwargs: state["audits"].append(
            {
                "event_type": event_type,
                "status": status,
                "message": message,
                **kwargs,
            }
        ),
    )

    monkeypatch.setattr(
        migration,
        "_existing_secret_values",
        lambda keys: {k: v for k, v in state["secrets"].items() if k in keys},
    )
    monkeypatch.setattr(
        migration,
        "_existing_secret_keys",
        lambda keys: [k for k in state["secrets"] if k in keys],
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


def test_unseedable_secrets_are_reported_by_name(seeded):
    """A stored GITHUB_PAT_TOKEN must be surfaced, not silently dropped."""
    seeded["secrets"] = {"GITHUB_PAT_TOKEN": "ghp_x", "SLACK_TOKEN": "xoxb-1"}

    assert migration.report_unseedable_secrets() == ["GITHUB_PAT_TOKEN"]


def test_nothing_is_reported_when_no_unmapped_secrets_exist(seeded):
    seeded["secrets"] = {"SLACK_TOKEN": "xoxb-1"}

    assert migration.report_unseedable_secrets() == []


def test_reporting_never_reads_secret_values(monkeypatch):
    """The report path must not decrypt.

    It only needs to know *which* keys exist, so it queries the key column
    alone. Decrypting here would put plaintext credentials one careless edit
    away from the log line built right below it.
    """
    monkeypatch.setattr(
        migration,
        "_existing_secret_values",
        lambda keys: pytest.fail("report_unseedable_secrets must not decrypt"),
    )
    monkeypatch.setattr(
        migration, "_existing_secret_keys", lambda keys: ["GITHUB_PAT_TOKEN"]
    )

    assert migration.report_unseedable_secrets() == ["GITHUB_PAT_TOKEN"]


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


# ------------------------------------------------------------------- auditing


def test_a_successful_seed_is_audited_with_field_names_only(seeded):
    """The audit row records which fields were seeded, never their values."""
    seeded["secrets"] = {"SMTP_HOST": "smtp.example.com", "SMTP_PASSWORD": "hunter2"}

    migration.seed_default_profile("smtp")

    event = seeded["audits"][0]
    assert event["event_type"] == "connector_profile.seed.succeeded"
    assert event["status"] == "success"
    assert event["connector_type"] == "smtp"
    assert event["seeded_fields"] == ["smtp_host", "smtp_password"]

    # The credentials themselves must not appear anywhere in the event.
    assert "hunter2" not in repr(event)
    assert "smtp.example.com" not in repr(event)


def test_a_validation_failure_is_audited(seeded, monkeypatch):
    """A best-effort skip still has to leave a record behind."""
    from m8flow_backend.services import connector_profile_service as service

    seeded["secrets"] = {"SMTP_HOST": "h"}

    def boom(body, user_id):
        raise service.ConnectorProfileError("missing password", status_code=400)

    monkeypatch.setattr(service.ConnectorProfileService, "create_profile", boom)

    assert migration.seed_default_profile("smtp") is None

    event = seeded["audits"][0]
    assert event["event_type"] == "connector_profile.seed.failed"
    assert event["status"] == "failed"
    assert event["severity"] == "warning"
    assert "missing password" in event["message"]


def test_an_unseedable_secret_is_audited_as_skipped(seeded):
    seeded["secrets"] = {"GITHUB_PAT_TOKEN": "ghp_x"}

    migration.report_unseedable_secrets()

    event = seeded["audits"][0]
    assert event["event_type"] == "connector_profile.seed.skipped"
    assert event["status"] == "skipped"
    assert event["secret_key"] == "GITHUB_PAT_TOKEN"
    assert "ghp_x" not in repr(event)


def test_audit_helper_actually_persists_a_row() -> None:
    """The tests above stub ``_audit``; this one exercises the real thing.

    Without it a mistake in the helper -- a bad column, a missing context guard
    -- would be invisible, because ``try_record_event`` swallows its own errors.

    A tenant-scoped request context is required because m8flow_audit_log carries
    m8f_tenant_id: the flush listener stamps it and refuses to write without one.
    That is exactly the context the only caller (the profile listing route) runs
    in.
    """
    from flask import Flask, g

    from m8flow_backend.models.audit_log import AuditLogModel
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: F401
    from m8flow_backend.models.process_model_bpmn_version import (  # noqa: F401
        ProcessModelBpmnVersionModel,
    )
    from spiffworkflow_backend.models.db import add_listeners, db

    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.test_request_context("/"):
        db.create_all()
        add_listeners()
        g.m8flow_tenant_id = "tenant-a"

        migration._audit(
            "connector_profile.seed.succeeded",
            "success",
            "Seeded the default smtp profile from existing secrets.",
            resource_id=7,
            connector_type="smtp",
            seeded_fields=["smtp_host", "smtp_password"],
        )

        row = AuditLogModel.query.one()
        assert row.category == migration.AUDIT_CATEGORY
        assert row.source == migration.AUDIT_SOURCE
        assert row.event_type == "connector_profile.seed.succeeded"
        assert row.status == "success"
        assert row.resource_id == "7"
        assert row.m8f_tenant_id == "tenant-a"
        assert row.details["seeded_fields"] == ["smtp_host", "smtp_password"]


def test_audit_outside_an_app_context_is_a_no_op() -> None:
    """Seeding must never fail because auditing could not run."""
    migration._audit("connector_profile.seed.failed", "failed", "offline")
