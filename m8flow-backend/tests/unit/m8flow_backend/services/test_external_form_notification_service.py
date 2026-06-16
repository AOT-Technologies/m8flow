"""Unit tests for ExternalFormNotificationService (M8F-339).

Tests cover:
- claim: atomic pending->notified transition, second claim refused (the
  never-duplicate-emails guarantee), submitted rows not claimable
- release_failed: revert to retryable failed state, no clobber after submit
- sweep_candidates: picks pending/notification-failed rows owed an email;
  excludes resume-failed (notified_at set), expired, exhausted, fresh rows
- build_secure_link: ref= appended preserving query params; mini-app base override
- notify: end-to-end with SMTP mocked, failure recording and retry
"""
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
    "SMTP_HOST": "smtp.test",
    "SMTP_PORT": "2525",
    "SMTP_FROM_EMAIL": "no-reply@tenant-one.example",
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
    def test_reverts_to_retryable_failed_state(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)

        ExternalFormNotificationService.release_failed(row.id, "connection refused")

        row = _fresh(row.id)
        assert row.status == ExternalFormRequestStatus.failed.value
        assert row.notified_at_in_seconds is None
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
        """Regression: M8F-338 _record_failure reuses status='failed' for workflow-resume
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
        smtp_secrets["SMTP_USERNAME"] = "mailuser"
        smtp_secrets["SMTP_PASSWORD"] = "mailpass"
        smtp_secrets["SMTP_STARTTLS"] = "true"
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

    def test_smtp_failure_releases_claim_for_retry(self, app, tenant, alice, fake_smtp, smtp_secrets):
        row = _create_request(tenant, alice)
        fake_smtp.fail_with = ConnectionRefusedError("smtp down")

        result = ExternalFormNotificationService.notify(row.reference_id)

        assert result.startswith("failed:")
        row = _fresh(row.id)
        assert row.status == ExternalFormRequestStatus.failed.value
        assert row.notified_at_in_seconds is None
        assert "smtp down" in row.last_error

        fake_smtp.fail_with = None
        assert ExternalFormNotificationService.notify(row.reference_id) == "sent"
        assert len(fake_smtp.sent_messages) == 1

    def test_unknown_reference(self, app):
        assert ExternalFormNotificationService.notify("no-such-ref") == "skipped:unknown_reference"

    def test_unconfigured_smtp_leaves_row_pending(self, app, tenant, alice, fake_smtp, smtp_secrets):
        smtp_secrets.clear()  # tenant has no SMTP secrets
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:smtp_unconfigured"
        assert _fresh(row.id).status == ExternalFormRequestStatus.pending.value

    def test_missing_from_email_is_unconfigured(self, app, tenant, alice, fake_smtp, smtp_secrets):
        del smtp_secrets["SMTP_FROM_EMAIL"]  # host present but no sender address
        row = _create_request(tenant, alice)

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:smtp_unconfigured"
        assert _fresh(row.id).status == ExternalFormRequestStatus.pending.value

    def test_expired_row_is_not_emailed(self, app, tenant, alice, fake_smtp, smtp_secrets):
        row = _create_request(tenant, alice, expires_at_in_seconds=int(time.time()) - 10)

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:expired"
        assert fake_smtp.sent_messages == []

    def test_non_http_link_is_refused_and_recorded(self, app, tenant, alice, fake_smtp, smtp_secrets):
        row = _create_request(tenant, alice, external_form_url="javascript:alert(1)")

        assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:unsafe_url"

        assert fake_smtp.sent_messages == []
        row = _fresh(row.id)
        assert row.status == ExternalFormRequestStatus.failed.value
        assert "not http/https" in row.last_error


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
