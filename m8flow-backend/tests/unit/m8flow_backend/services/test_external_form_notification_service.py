"""Unit tests for ExternalFormNotificationService.

Tests cover:
- claim: atomic pending->notified transition, second claim refused (the
  never-duplicate-emails guarantee), submitted rows not claimable
- release_failed: revert to retryable failed state, no clobber after submit
- sweep_candidates: picks pending/notification-failed rows owed an email;
  excludes resume-failed (notified_at set), expired, exhausted, fresh rows
- build_secure_link: ref= appended preserving query params; mini-app base override
- notify: end-to-end with SMTP mocked, failure recording and retry
- smtp_unconfigured: unconfigured tenants park terminally instead of retrying forever,
  and revive/requeue bring parked rows back
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
# Imported for its side effect of registering the `secret` table before db.create_all():
# smtp_configuration_status() presence-checks optional keys against it.
from spiffworkflow_backend.models.secret_model import SecretModel  # noqa: E402,F401
from spiffworkflow_backend.models.user import UserModel  # noqa: E402

from m8flow_backend.models.external_form_request import (  # noqa: E402
    ExternalFormRequestModel,
    ExternalFormRequestStatus,
)
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
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
    """Stub the per-tenant SMTP secret lookup with a mutable dict (default: configured).

    Mirrors the real _read_tenant_secret, which strips the decrypted value and reports a
    blank one as absent — a whitespace-only secret must not read as configured."""

    secrets = dict(DEFAULT_SMTP_SECRETS)

    def read(key):
        value = (secrets.get(key) or "").strip()
        return value or None

    monkeypatch.setattr(ExternalFormNotificationService, "_read_tenant_secret", staticmethod(read))
    return secrets


@pytest.fixture
def app():
    """Create Flask app with in-memory database for testing."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
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
        # Failure reason is logged (not stored on the row).
        assert "connection refused" in caplog.text

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
        # Failure reason is both logged and stored, so an admin can diagnose from the UI.
        assert "smtp down" in caplog.text
        assert "smtp down" in row.last_error

        fake_smtp.fail_with = None
        assert ExternalFormNotificationService.notify(row.reference_id) == "sent"
        assert len(fake_smtp.sent_messages) == 1
        # A successful claim clears the stale diagnosis.
        assert _fresh(row.id).last_error is None

    def test_unknown_reference(self, app):
        assert ExternalFormNotificationService.notify("no-such-ref") == "skipped:unknown_reference"

    def test_unconfigured_smtp_parks_row_terminally(self, app, tenant, alice, fake_smtp, smtp_secrets):
        smtp_secrets.clear()  # tenant has no SMTP secrets
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:smtp_unconfigured"
        parked = _fresh(row.id)
        assert parked.status == ExternalFormRequestStatus.smtp_unconfigured.value
        assert parked.attempts == 0  # no real delivery was attempted
        assert "NATS_SMTP_HOST" in parked.last_error

    def test_missing_from_email_is_unconfigured(self, app, tenant, alice, fake_smtp, smtp_secrets):
        del smtp_secrets["NATS_SMTP_FROM_EMAIL"]  # host present but no sender address
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:smtp_unconfigured"
        parked = _fresh(row.id)
        assert parked.status == ExternalFormRequestStatus.smtp_unconfigured.value
        # Only the genuinely missing key is reported; the configured host is not.
        assert "NATS_SMTP_FROM_EMAIL" in parked.last_error
        assert "NATS_SMTP_HOST" not in parked.last_error

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
        assert "not http/https" in caplog.text
        assert "not http/https" in row.last_error


class TestSmtpUnconfigured:
    """The behaviour that ends the silent-infinite-retry bug."""

    def test_parked_row_is_invisible_to_the_sweep(self, app, tenant, alice, fake_smtp, smtp_secrets):
        smtp_secrets.clear()
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.notify(row.reference_id)

        # Well past the grace period, so only the status can be keeping it out.
        later = int(time.time()) + 100_000
        candidates = ExternalFormNotificationService.sweep_candidates(now=later)

        assert [candidate for candidate in candidates if candidate[0] == row.id] == []

    def test_mark_does_not_clobber_a_claimed_row(self, app, tenant, alice, smtp_secrets):
        row = _create_request(tenant, alice)
        assert ExternalFormNotificationService.claim(row.id) is True

        assert ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "Missing required secrets: NATS_SMTP_HOST") == 0
        assert _fresh(row.id).status == ExternalFormRequestStatus.notified.value

    def test_revive_returns_parked_rows_to_the_queue(self, app, tenant, alice, fake_smtp, smtp_secrets):
        smtp_secrets.clear()
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.notify(row.reference_id)

        smtp_secrets.update(DEFAULT_SMTP_SECRETS)  # admin configures SMTP
        assert ExternalFormNotificationService.revive_smtp_unconfigured() == 1

        revived = _fresh(row.id)
        assert revived.status == ExternalFormRequestStatus.pending.value
        assert revived.attempts == 0
        assert revived.last_error is None
        assert ExternalFormNotificationService.notify(row.reference_id) == "sent"

    def test_revive_leaves_other_statuses_alone(self, app, tenant, alice, smtp_secrets):
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.revive_smtp_unconfigured() == 0
        assert _fresh(row.id).status == ExternalFormRequestStatus.pending.value

    def test_tenants_with_parked_requests(self, app, tenant, alice, fake_smtp, smtp_secrets):
        smtp_secrets.clear()
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.tenants_with_parked_requests() == []

        ExternalFormNotificationService.notify(row.reference_id)

        assert ExternalFormNotificationService.tenants_with_parked_requests() == [tenant.id]

    def test_missing_required_smtp_keys(self, app, tenant, smtp_secrets):
        assert ExternalFormNotificationService.missing_required_smtp_keys() == []

        smtp_secrets["NATS_SMTP_HOST"] = "   "  # present but blank is not usable

        assert ExternalFormNotificationService.missing_required_smtp_keys() == ["NATS_SMTP_HOST"]

    def test_status_reports_keys_never_values(self, app, tenant, smtp_secrets):
        status = ExternalFormNotificationService.smtp_configuration_status()

        assert status["configured"] is True
        assert status["missing_required_keys"] == []
        assert status["required_keys"] == ["NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"]
        assert "NATS_SMTP_PASSWORD" in status["optional_keys"]
        assert [field["secretKey"] for field in status["fields"]]
        serialized = str(status)
        for value in DEFAULT_SMTP_SECRETS.values():
            assert value not in serialized

    def test_status_lists_missing_required_keys(self, app, tenant, smtp_secrets):
        smtp_secrets.clear()

        status = ExternalFormNotificationService.smtp_configuration_status()

        assert status["configured"] is False
        assert status["missing_required_keys"] == ["NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"]


class TestRequeue:
    def test_requeues_a_parked_row(self, app, tenant, alice, fake_smtp, smtp_secrets):
        smtp_secrets.clear()
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.notify(row.reference_id)

        assert ExternalFormNotificationService.requeue(row.id) is True
        assert _fresh(row.id).status == ExternalFormRequestStatus.pending.value

    def test_requeues_a_send_failure(self, app, tenant, alice, fake_smtp, smtp_secrets):
        row = _create_request(tenant, alice)
        fake_smtp.fail_with = ConnectionRefusedError("smtp down")
        ExternalFormNotificationService.notify(row.reference_id)

        assert ExternalFormNotificationService.requeue(row.id) is True
        requeued = _fresh(row.id)
        assert requeued.status == ExternalFormRequestStatus.pending.value
        assert requeued.attempts == 0
        assert requeued.last_error is None

    def test_refuses_an_already_notified_row(self, app, tenant, alice, fake_smtp, smtp_secrets):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.notify(row.reference_id)

        assert ExternalFormNotificationService.requeue(row.id) is False
        assert _fresh(row.id).status == ExternalFormRequestStatus.notified.value

    def test_refuses_a_failed_resume(self, app, tenant, alice, smtp_secrets):
        """A 'failed' row that kept notified_at is a failed workflow resume, not a failed
        send — the recipient already got their email and must not get a second one."""
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)
        row = _fresh(row.id)
        row.status = ExternalFormRequestStatus.failed.value
        db.session.commit()

        assert ExternalFormNotificationService.requeue(row.id) is False


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
