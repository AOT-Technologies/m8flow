"""Unit tests for ExternalFormNotificationService.

Tests cover:
- claim: atomic pending->notified transition, second claim refused (the
  never-duplicate-emails guarantee), submitted rows not claimable
- release_failed: revert to retryable failed state, no clobber after submit
- sweep_candidates: picks pending/notification-failed rows owed an email;
  excludes resume-failed (notified_at set), expired, exhausted, fresh rows
- build_secure_link: ref= appended preserving query params; mini-app base override
- notify: end-to-end with SMTP mocked, failure recording and retry
- smtp_readiness / smtp_configuration_status: missing vs unreadable required secrets
- mark_smtp_unconfigured / revive_smtp_unconfigured / requeue: the terminal park that
  stops the indefinite retry loop, and the paths back out of it
"""
import logging
import sys
import time
from pathlib import Path

import pytest
from flask import Flask

# Setup path for imports
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.models.db import add_listeners  # noqa: E402
from spiffworkflow_backend.models.user import UserModel  # noqa: E402

from m8flow_backend.models.external_form_request import (  # noqa: E402
    LAST_ERROR_MAX_LENGTH,
    ExternalFormRequestModel,
    ExternalFormRequestStatus,
)
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from m8flow_backend.models.process_model_bpmn_version import (  # noqa: E402, F401
    ProcessModelBpmnVersionModel,
)
from m8flow_backend.services.external_form_notification_service import (  # noqa: E402
    ExternalFormNotificationService,
)
from m8flow_backend.services.external_form_service import ExternalFormService  # noqa: E402

TASK_GUID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def _notification_env(monkeypatch):
    monkeypatch.setenv("M8FLOW_EXTERNAL_FORM_LINK_TTL_SECONDS", "604800")


# Default per-tenant SMTP secrets used by the configured-tenant tests. SMTP is resolved
# from the tenant's encrypted secrets, so we stub _read_tenant_secret instead of env.
DEFAULT_SMTP_SECRETS = {
    "NATS_SMTP_HOST": "smtp.test",
    "NATS_SMTP_PORT": "2525",
    "NATS_SMTP_FROM_EMAIL": "no-reply@tenant-one.example",
}


@pytest.fixture
def smtp_secrets(monkeypatch):
    """Stub the per-tenant SMTP secret lookup with a mutable dict (default: configured)."""
    secrets = dict(DEFAULT_SMTP_SECRETS)
    monkeypatch.setattr(
        ExternalFormNotificationService,
        "_read_tenant_secret",
        staticmethod(lambda key: secrets.get(key)),
    )
    return secrets


@pytest.fixture
def app():
    """Create Flask app with in-memory database for testing."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    app.config["SPIFFWORKFLOW_BACKEND_ENCRYPTION_LIB"] = "no_op_cipher"
    from spiffworkflow_backend.config import NoOpCipher

    app.config["CIPHER"] = NoOpCipher()
    db.init_app(app)

    with app.app_context():
        db.create_all()
        add_listeners()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def tenant(app):
    tenant = M8flowTenantModel(
        id="tenant-1",
        name="Tenant One",
        slug="tenant-one",
        status=TenantStatus.ACTIVE,
        created_by="admin",
        modified_by="admin",
    )
    db.session.add(tenant)
    db.session.commit()
    return tenant


@pytest.fixture
def alice(app):
    user = UserModel(username="alice", service="test", service_id="alice", email="alice@example.com")
    db.session.add(user)
    db.session.commit()
    return user


class FakeSMTP:
    """Stand-in for smtplib.SMTP/SMTP_SSL capturing sent messages."""

    sent_messages: list = []
    fail_with: Exception | None = None
    login_calls: list = []
    starttls_calls: int = 0
    connected_to: tuple | None = None

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        FakeSMTP.connected_to = (host, port)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        FakeSMTP.starttls_calls += 1

    def login(self, username, password):
        FakeSMTP.login_calls.append((username, password))

    def send_message(self, message):
        if FakeSMTP.fail_with is not None:
            raise FakeSMTP.fail_with
        FakeSMTP.sent_messages.append(message)


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.sent_messages = []
    FakeSMTP.fail_with = None
    FakeSMTP.login_calls = []
    FakeSMTP.starttls_calls = 0
    FakeSMTP.connected_to = None
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("smtplib.SMTP_SSL", FakeSMTP)
    return FakeSMTP


def _create_request(tenant, user, **kwargs):
    defaults = {
        "tenant_id": tenant.id,
        "process_instance_id": 42,
        "task_guid": TASK_GUID,
        "external_form_url": "https://forms.example.com/leave-request",
        "recipients": [{"user_id": user.id, "email": user.email, "user_details": {"username": user.username}}],
    }
    defaults.update(kwargs)
    return ExternalFormService.create_requests_for_task(**defaults)[0]


def _fresh(row_id):
    db.session.expire_all()
    return db.session.get(ExternalFormRequestModel, row_id)


class TestClaim:
    def test_claim_marks_notified_and_increments_attempts(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.claim(row.id) is True

        row = _fresh(row.id)
        assert row.status == ExternalFormRequestStatus.notified.value
        assert row.notified_at_in_seconds is not None
        assert row.attempts == 1

    def test_second_claim_is_refused(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.claim(row.id) is True
        assert ExternalFormNotificationService.claim(row.id) is False
        assert _fresh(row.id).attempts == 1

    def test_submitted_row_is_not_claimable(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        row.status = ExternalFormRequestStatus.submitted.value
        db.session.commit()

        assert ExternalFormNotificationService.claim(row.id) is False

    def test_notification_failed_row_is_claimable_again(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        assert ExternalFormNotificationService.claim(row.id) is True
        ExternalFormNotificationService.release_failed(row.id, "smtp down")

        assert ExternalFormNotificationService.claim(row.id) is True
        assert _fresh(row.id).attempts == 2


class TestReleaseFailed:
    def test_reverts_to_retryable_failed_state(self, app, tenant, alice, caplog):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)

        with caplog.at_level(logging.WARNING):
            ExternalFormNotificationService.release_failed(row.id, "connection refused")

        row = _fresh(row.id)
        assert row.status == ExternalFormRequestStatus.failed.value
        assert row.notified_at_in_seconds is None
        # Failure reason is both logged and persisted for the admin UI.
        assert "connection refused" in caplog.text
        assert row.last_error == "connection refused"

    def test_does_not_clobber_submitted_row(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)
        row = _fresh(row.id)
        row.status = ExternalFormRequestStatus.submitted.value
        db.session.commit()

        ExternalFormNotificationService.release_failed(row.id, "late failure")

        row = _fresh(row.id)
        assert row.status == ExternalFormRequestStatus.submitted.value
        assert row.notified_at_in_seconds is not None


class TestSweepCandidates:
    def _sweep_now(self):
        # Far enough ahead that just-created rows clear the grace window, but well
        # before the 7-day link TTL.
        return int(time.time()) + 1000

    def test_picks_up_pending_rows_after_grace(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        candidates = ExternalFormNotificationService.sweep_candidates(now=self._sweep_now())

        assert [(row.id, row.reference_id, tenant.id)] == candidates

    def test_skips_rows_within_grace_window(self, app, tenant, alice):
        _create_request(tenant, alice)

        assert ExternalFormNotificationService.sweep_candidates(now=int(time.time())) == []

    def test_picks_up_notification_failed_rows(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)
        ExternalFormNotificationService.release_failed(row.id, "smtp down")

        candidates = ExternalFormNotificationService.sweep_candidates(now=self._sweep_now())

        assert [c[0] for c in candidates] == [row.id]

    def test_never_picks_up_resume_failed_rows(self, app, tenant, alice):
        """Regression: _record_failure reuses status='failed' for workflow-resume
        failures, which only happen after the email went out. notified_at stays set, so
        the sweep must not re-email."""
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)
        row = _fresh(row.id)
        row.status = ExternalFormRequestStatus.failed.value  # resume failure keeps notified_at
        db.session.commit()

        assert ExternalFormNotificationService.sweep_candidates(now=self._sweep_now()) == []

    def test_skips_notified_submitted_completed_and_superseded(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        for status in ("notified", "submitted", "completed", "superseded"):
            row.status = status
            db.session.commit()
            assert ExternalFormNotificationService.sweep_candidates(now=self._sweep_now()) == []

    def test_skips_expired_rows(self, app, tenant, alice):
        _create_request(tenant, alice, expires_at_in_seconds=int(time.time()) - 10)

        assert ExternalFormNotificationService.sweep_candidates(now=self._sweep_now() - 1000) == []

    def test_skips_rows_with_exhausted_attempts(self, app, tenant, alice, monkeypatch):
        monkeypatch.setenv("M8FLOW_NOTIFICATION_MAX_ATTEMPTS", "2")
        row = _create_request(tenant, alice)
        for _ in range(2):
            ExternalFormNotificationService.claim(row.id)
            ExternalFormNotificationService.release_failed(row.id, "smtp down")

        assert ExternalFormNotificationService.sweep_candidates(now=self._sweep_now()) == []


class TestBuildSecureLink:
    def test_appends_ref_to_external_form_url(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        link = ExternalFormNotificationService.build_secure_link(row)

        assert link == f"https://forms.example.com/leave-request?ref={row.reference_id}"

    def test_preserves_existing_query_params(self, app, tenant, alice):
        row = _create_request(tenant, alice, external_form_url="https://forms.example.com/f?lang=en")

        link = ExternalFormNotificationService.build_secure_link(row)

        assert link == f"https://forms.example.com/f?lang=en&ref={row.reference_id}"


class TestNotify:
    def test_sends_email_and_marks_notified(self, app, tenant, alice, fake_smtp, smtp_secrets):
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.notify(row.reference_id) == "sent"

        row = _fresh(row.id)
        assert row.status == ExternalFormRequestStatus.notified.value
        assert row.notified_at_in_seconds is not None
        assert len(fake_smtp.sent_messages) == 1
        message = fake_smtp.sent_messages[0]
        assert message["To"] == "alice@example.com"
        assert message["From"] == "no-reply@tenant-one.example"
        assert row.reference_id in message.get_body(("html",)).get_content()

    def test_uses_tenant_smtp_host_port_and_login(self, app, tenant, alice, fake_smtp, smtp_secrets):
        smtp_secrets["NATS_SMTP_USERNAME"] = "mailuser"
        smtp_secrets["NATS_SMTP_PASSWORD"] = "mailpass"
        smtp_secrets["NATS_SMTP_STARTTLS"] = "true"
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.notify(row.reference_id) == "sent"

        assert fake_smtp.connected_to == ("smtp.test", 2525)
        assert fake_smtp.starttls_calls == 1
        assert fake_smtp.login_calls == [("mailuser", "mailpass")]

    def test_second_notify_sends_nothing(self, app, tenant, alice, fake_smtp, smtp_secrets):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.notify(row.reference_id)

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:not_claimable"
        assert len(fake_smtp.sent_messages) == 1

    def test_smtp_failure_releases_claim_for_retry(self, app, tenant, alice, fake_smtp, smtp_secrets, caplog):
        row = _create_request(tenant, alice)
        fake_smtp.fail_with = ConnectionRefusedError("smtp down")

        with caplog.at_level(logging.WARNING):
            result = ExternalFormNotificationService.notify(row.reference_id)

        assert result.startswith("failed:")
        row = _fresh(row.id)
        assert row.status == ExternalFormRequestStatus.failed.value
        assert row.notified_at_in_seconds is None
        # Failure reason is both logged and persisted for the admin UI.
        assert "smtp down" in caplog.text
        assert row.last_error is not None and "smtp down" in row.last_error

        fake_smtp.fail_with = None
        assert ExternalFormNotificationService.notify(row.reference_id) == "sent"
        assert len(fake_smtp.sent_messages) == 1

    def test_unknown_reference(self, app):
        assert ExternalFormNotificationService.notify("no-such-ref") == "skipped:unknown_reference"

    def test_unconfigured_smtp_parks_row_as_terminal(self, app, tenant, alice, fake_smtp, smtp_secrets, caplog):
        """The regression test for the indefinite retry loop.

        Leaving the row 'pending' meant claim() never ran, so attempts stayed 0 and
        sweep_candidates re-selected it every interval for the link's whole TTL."""
        smtp_secrets.clear()  # tenant has no SMTP secrets
        row = _create_request(tenant, alice)

        with caplog.at_level(logging.ERROR):
            assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:smtp_unconfigured"

        parked = _fresh(row.id)
        assert parked.status == ExternalFormRequestStatus.smtp_unconfigured.value
        assert parked.last_error is not None
        assert "NATS_SMTP_HOST" in parked.last_error
        assert fake_smtp.sent_messages == []
        # Logged once, with the identifiers an admin needs and no secret values.
        assert "smtp_unconfigured" in caplog.text
        assert str(tenant.id) in caplog.text

    def test_parked_row_is_not_swept_again(self, app, tenant, alice, fake_smtp, smtp_secrets, monkeypatch):
        """A parked row must fall out of sweep_candidates entirely — this is what ends the
        retry loop. Asserted against the query itself, not only via notify()."""
        monkeypatch.setenv("M8FLOW_NOTIFICATION_SWEEP_GRACE_SECONDS", "0")
        smtp_secrets.clear()
        row = _create_request(tenant, alice)
        now = int(time.time()) + 1000

        # Owed an email before the park...
        assert row.id in [candidate[0] for candidate in ExternalFormNotificationService.sweep_candidates(now=now)]

        ExternalFormNotificationService.notify(row.reference_id)

        # ...and invisible to every subsequent sweep.
        assert ExternalFormNotificationService.sweep_candidates(now=now) == []


    def test_redelivered_event_cannot_email_a_parked_row(
        self, app, tenant, alice, fake_smtp, smtp_secrets
    ):
        """A parked row is outside CLAIMABLE_STATUSES, so the NATS fast path cannot email
        it even after SMTP is configured. Recovery must go through revive/resend, which is
        what keeps the parked state authoritative while events are still in flight."""
        smtp_secrets.clear()
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.notify(row.reference_id)
        assert _fresh(row.id).status == ExternalFormRequestStatus.smtp_unconfigured.value

        smtp_secrets.update(DEFAULT_SMTP_SECRETS)

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:not_claimable"
        assert fake_smtp.sent_messages == []
        assert _fresh(row.id).status == ExternalFormRequestStatus.smtp_unconfigured.value

    def test_missing_from_email_is_unconfigured(self, app, tenant, alice, fake_smtp, smtp_secrets):
        del smtp_secrets["NATS_SMTP_FROM_EMAIL"]  # host present but no sender address
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:smtp_unconfigured"
        parked = _fresh(row.id)
        assert parked.status == ExternalFormRequestStatus.smtp_unconfigured.value
        assert "NATS_SMTP_FROM_EMAIL" in parked.last_error

    def test_expired_row_is_not_emailed(self, app, tenant, alice, fake_smtp, smtp_secrets):
        row = _create_request(tenant, alice, expires_at_in_seconds=int(time.time()) - 10)

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:expired"
        assert fake_smtp.sent_messages == []

    def test_non_http_link_is_refused_and_recorded(self, app, tenant, alice, fake_smtp, smtp_secrets, caplog):
        row = _create_request(tenant, alice, external_form_url="javascript:alert(1)")

        with caplog.at_level(logging.WARNING):
            assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:unsafe_url"

        assert fake_smtp.sent_messages == []
        row = _fresh(row.id)
        assert row.status == ExternalFormRequestStatus.failed.value
        # Failure reason is both logged and persisted for the admin UI.
        assert "not http/https" in caplog.text
        assert row.last_error is not None and "not http/https" in row.last_error


class TestRenderEmail:
    def test_includes_task_and_process_labels(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        class FakeHumanTask:
            task_title = "Approve leave"
            task_name = "approve_leave"
            process_model_display_name = "Leave Request"

        subject, text_body, html_body = ExternalFormNotificationService.render_email(row, FakeHumanTask())

        assert subject == "Action required: Approve leave — Leave Request"
        for body in (text_body, html_body):
            assert "Approve leave" in body
            assert row.reference_id in body
        assert "alice" in text_body

    def test_falls_back_without_human_task(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        subject, text_body, _ = ExternalFormNotificationService.render_email(row, None)

        assert subject == "Action required: a task needs your input"
        assert row.reference_id in text_body

    def test_html_body_escapes_modeler_and_identity_controlled_values(self, app, tenant, alice):
        """Recipient name and task/process labels must not inject markup into the HTML part."""
        row = _create_request(tenant, alice)
        row.user_details = {"username": '<script>alert("x")</script>'}
        db.session.commit()

        class FakeHumanTask:
            task_title = '<img src=x onerror="steal()">'
            task_name = "approve_leave"
            process_model_display_name = "Leave & \"Absence\""

        _, _, html_body = ExternalFormNotificationService.render_email(row, FakeHumanTask())

        assert "<script>" not in html_body
        assert "<img src=x" not in html_body
        assert "&lt;script&gt;" in html_body
        assert "&lt;img src=x" in html_body

    def test_html_body_escapes_link_in_href(self, app, tenant, alice):
        row = _create_request(tenant, alice, external_form_url='https://forms.example.com/f?a=1&b="><script>')

        _, _, html_body = ExternalFormNotificationService.render_email(row, None)

        assert "<script>" not in html_body
        assert "&amp;" in html_body


def _add_secret(tenant_id: str, key: str, raw_value: str) -> None:
    """Write a real encrypted SecretModel row so the presence query sees it."""
    from spiffworkflow_backend.models.secret_model import SecretModel
    from spiffworkflow_backend.services.secret_service import SecretService

    secret = SecretModel(key=key, value=SecretService._encrypt(raw_value), user_id=1)
    secret.m8f_tenant_id = tenant_id
    db.session.add(secret)
    db.session.commit()


class TestSmtpReadiness:
    """Missing vs unreadable required secrets.

    Both block sending but need opposite fixes -- re-entering a key does not help when the
    stored value cannot be decrypted -- so the reason must never collapse them.
    """

    def test_no_secrets_reports_every_required_key_missing(self, app, tenant, smtp_secrets):
        smtp_secrets.clear()

        readiness = ExternalFormNotificationService.smtp_readiness()

        assert readiness["ok"] is False
        assert set(readiness["missing"]) == {"NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"}
        assert readiness["unreadable"] == []
        assert "Missing required secrets" in readiness["reason"]

    def test_configured_tenant_is_ok(self, app, tenant, smtp_secrets):
        readiness = ExternalFormNotificationService.smtp_readiness()

        assert readiness["ok"] is True
        assert readiness["unusable"] == []
        assert readiness["reason"] is None

    def test_present_but_blank_secret_is_unreadable_not_missing(self, app, tenant, monkeypatch):
        """A row exists yet resolves to nothing. Reporting it as missing would send the
        admin to re-enter a key that is already there."""
        _add_secret(tenant.id, "NATS_SMTP_HOST", "smtp.test")
        _add_secret(tenant.id, "NATS_SMTP_FROM_EMAIL", "   ")
        monkeypatch.setattr(
            ExternalFormNotificationService,
            "_read_tenant_secret",
            staticmethod(lambda key: {"NATS_SMTP_HOST": "smtp.test"}.get(key)),
        )

        readiness = ExternalFormNotificationService.smtp_readiness()

        assert readiness["ok"] is False
        assert readiness["missing"] == []
        assert readiness["unreadable"] == ["NATS_SMTP_FROM_EMAIL"]
        assert "encryption key changed" in readiness["reason"]

    def test_configuration_status_returns_names_never_values(self, app, tenant, smtp_secrets):
        status = ExternalFormNotificationService.smtp_configuration_status()

        assert status["configured"] is True
        assert status["required_keys"] == ["NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"]
        assert "NATS_SMTP_PASSWORD" in status["optional_keys"]
        # No secret value may appear anywhere in the payload.
        assert "smtp.test" not in repr(status)

    def test_required_keys_match_resolve_smtp_settings(self, app, tenant, smtp_secrets):
        """Guards the single-source-of-truth invariant: if these drift, the API would
        report a tenant as configured when it still cannot send."""
        for key in ExternalFormNotificationService.smtp_configuration_status()["required_keys"]:
            secrets = dict(DEFAULT_SMTP_SECRETS)
            del secrets[key]
            smtp_secrets.clear()
            smtp_secrets.update(secrets)
            assert ExternalFormNotificationService.resolve_smtp_settings() is None


class TestMarkSmtpUnconfigured:
    def test_parks_pending_rows(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no smtp") == 1
        parked = _fresh(row.id)
        assert parked.status == ExternalFormRequestStatus.smtp_unconfigured.value
        assert parked.last_error == "no smtp"

    def test_does_not_clobber_claimed_row(self, app, tenant, alice):
        """Mirrors the release_failed guard: another worker already owns this row."""
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)

        assert ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no smtp") == 0
        assert _fresh(row.id).status == ExternalFormRequestStatus.notified.value

    def test_does_not_clobber_submitted_row(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        row = _fresh(row.id)
        row.status = ExternalFormRequestStatus.submitted.value
        db.session.commit()

        assert ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no smtp") == 0
        assert _fresh(row.id).status == ExternalFormRequestStatus.submitted.value

    def test_empty_id_list_is_a_noop(self, app, tenant):
        assert ExternalFormNotificationService.mark_smtp_unconfigured([], "no smtp") == 0

    def test_long_reason_is_truncated_to_the_column(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "x" * 5000)

        assert len(_fresh(row.id).last_error) == LAST_ERROR_MAX_LENGTH


class TestReviveSmtpUnconfigured:
    def test_bulk_revive_requires_tenant_id(self, app, tenant, alice):
        """UPDATEs bypass the tenant-scoping SELECT listener, so an unscoped bulk revive
        would unpark every tenant's rows."""
        with pytest.raises(ValueError, match="requires tenant_id"):
            ExternalFormNotificationService.revive_smtp_unconfigured()

    def test_revives_parked_rows_and_resets_attempts(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no smtp")

        assert ExternalFormNotificationService.revive_smtp_unconfigured(tenant_id=tenant.id) == 1
        revived = _fresh(row.id)
        assert revived.status == ExternalFormRequestStatus.pending.value
        assert revived.notified_at_in_seconds is None
        # The parked attempts burned no SMTP connection, so they must not count.
        assert revived.attempts == 0
        assert revived.last_error is None

    def test_leaves_other_tenants_parked_rows_alone(self, app, tenant, alice):
        other = M8flowTenantModel(
            id="tenant-2",
            name="Tenant Two",
            slug="tenant-two",
            status=TenantStatus.ACTIVE,
            created_by="admin",
            modified_by="admin",
        )
        db.session.add(other)
        db.session.commit()
        mine = _create_request(tenant, alice)
        theirs = _create_request(other, alice, process_instance_id=99)
        ExternalFormNotificationService.mark_smtp_unconfigured([mine.id, theirs.id], "no smtp")

        assert ExternalFormNotificationService.revive_smtp_unconfigured(tenant_id=tenant.id) == 1

        assert _fresh(mine.id).status == ExternalFormRequestStatus.pending.value
        assert _fresh(theirs.id).status == ExternalFormRequestStatus.smtp_unconfigured.value

    def test_does_not_touch_non_parked_rows(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.revive_smtp_unconfigured(tenant_id=tenant.id) == 0
        assert _fresh(row.id).status == ExternalFormRequestStatus.pending.value

    def test_tenants_with_parked_requests(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        assert ExternalFormNotificationService.tenants_with_parked_requests() == []

        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no smtp")

        assert ExternalFormNotificationService.tenants_with_parked_requests() == [tenant.id]

    def test_revived_row_is_delivered_on_the_next_sweep(
        self, app, tenant, alice, fake_smtp, smtp_secrets, monkeypatch
    ):
        """End-to-end recovery: park while unconfigured, then deliver once fixed."""
        monkeypatch.setenv("M8FLOW_NOTIFICATION_SWEEP_GRACE_SECONDS", "0")
        smtp_secrets.clear()
        row = _create_request(tenant, alice)
        now = int(time.time()) + 1000
        ExternalFormNotificationService.notify(row.reference_id)
        assert _fresh(row.id).status == ExternalFormRequestStatus.smtp_unconfigured.value

        smtp_secrets.update(DEFAULT_SMTP_SECRETS)
        ExternalFormNotificationService.revive_smtp_unconfigured(tenant_id=tenant.id)

        assert row.id in [candidate[0] for candidate in ExternalFormNotificationService.sweep_candidates(now=now)]
        assert ExternalFormNotificationService.notify(row.reference_id) == "sent"
        assert len(fake_smtp.sent_messages) == 1


class TestRequeue:
    def test_requeues_a_parked_row(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no smtp")

        assert ExternalFormNotificationService.requeue(row.id, tenant_id=tenant.id) is True
        requeued = _fresh(row.id)
        assert requeued.status == ExternalFormRequestStatus.pending.value
        assert requeued.attempts == 0
        assert requeued.last_error is None

    def test_requeues_a_failed_send(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)
        ExternalFormNotificationService.release_failed(row.id, "smtp down")

        assert ExternalFormNotificationService.requeue(row.id, tenant_id=tenant.id) is True
        assert _fresh(row.id).status == ExternalFormRequestStatus.pending.value

    def test_refuses_a_failed_resume(self, app, tenant, alice):
        """A failed row that still has notified_at set is a failed workflow *resume*, not a
        failed send. It was already emailed, so re-emailing it is wrong."""
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)
        row = _fresh(row.id)
        row.status = ExternalFormRequestStatus.failed.value
        db.session.commit()
        assert _fresh(row.id).notified_at_in_seconds is not None

        assert ExternalFormNotificationService.requeue(row.id, tenant_id=tenant.id) is False
        assert _fresh(row.id).status == ExternalFormRequestStatus.failed.value

    def test_refuses_a_submitted_row(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        row = _fresh(row.id)
        row.status = ExternalFormRequestStatus.submitted.value
        db.session.commit()

        assert ExternalFormNotificationService.requeue(row.id, tenant_id=tenant.id) is False

    def test_tenant_id_pins_the_update(self, app, tenant, alice):
        """request_id is a bare integer, so without the filter a super admin could requeue
        any tenant's row."""
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no smtp")

        assert ExternalFormNotificationService.requeue(row.id, tenant_id="tenant-other") is False
        assert _fresh(row.id).status == ExternalFormRequestStatus.smtp_unconfigured.value
