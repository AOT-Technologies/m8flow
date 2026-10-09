"""Tenant resolution for the notification worker's SMTP lookup.

The worker runs outside any request context and sets the active tenant in the
ContextVar (`set_context_tenant_id`), so a `g`-only read of the tenant id found
nothing and every send reported `skipped:smtp_unconfigured` -- the tenant's
NATS_SMTP_* secrets were configured and still never used. These tests pin the
`get_tenant_id()` resolution, exercising both the worker's non-request shape and
the request shape a route provides.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from flask import g

from m8flow_backend.auth.tenant_context import reset_context_tenant_id, set_context_tenant_id
from m8flow_backend.secrets import add_secret
from m8flow_backend.services.external_form_notification_service import (
    ExternalFormNotificationService,
)
from m8flow_backend.services import external_form_notification_service as notification_service

TENANT = "t1"


@pytest.fixture
def _tenant_smtp_secrets(db_session):
    from m8flow_backend.identity import ensure_user

    user = ensure_user(
        db_session,
        username="alice",
        service="https://example.test/realms/m8flow",
        service_id="alice",
    )
    for key, value in (
        ("NATS_SMTP_HOST", "smtp.example.test"),
        ("NATS_SMTP_FROM_EMAIL", "noreply@example.test"),
        ("NATS_SMTP_PORT", "2525"),
        ("NATS_SMTP_STARTTLS", "true"),
    ):
        add_secret(db_session, tenant_id=TENANT, key=key, value=value, user_id=user.id)
    db_session.commit()
    return user


def test_resolve_smtp_settings_uses_the_context_tenant_outside_a_request(
    app, _tenant_smtp_secrets
):
    """The worker's shape: app context only, tenant in the ContextVar."""
    with app.app_context():
        token = set_context_tenant_id(TENANT)
        try:
            settings = ExternalFormNotificationService.resolve_smtp_settings()
        finally:
            reset_context_tenant_id(token)

    assert settings is not None
    assert settings["host"] == "smtp.example.test"
    assert settings["from_email"] == "noreply@example.test"
    assert settings["port"] == 2525
    assert settings["starttls"] is True


def test_resolve_smtp_settings_still_uses_the_request_tenant(app, db_session, _tenant_smtp_secrets):
    with app.test_request_context("/"):
        g.db_session = db_session
        g.m8flow_tenant_id = TENANT
        settings = ExternalFormNotificationService.resolve_smtp_settings()

    assert settings is not None
    assert settings["host"] == "smtp.example.test"


def test_resolve_smtp_settings_is_none_without_an_active_tenant(app, _tenant_smtp_secrets):
    """No tenant at all must read as "not configured", never raise."""
    with app.app_context():
        assert ExternalFormNotificationService.resolve_smtp_settings() is None


def test_resolve_smtp_settings_is_none_for_a_tenant_without_secrets(app, _tenant_smtp_secrets):
    with app.app_context():
        token = set_context_tenant_id("other-tenant")
        try:
            assert ExternalFormNotificationService.resolve_smtp_settings() is None
        finally:
            reset_context_tenant_id(token)


# ---------------------------------------------------------------------------
# Parking lifecycle: a tenant with no usable SMTP config must not be retried
# forever, and must recover by itself once the secrets appear.
# ---------------------------------------------------------------------------


def _request_row(db_session, *, tenant_id=TENANT, status="pending", created_at=0, notified_at=None):
    from m8flow_backend.models.external_form_request import ExternalFormRequestModel

    row = ExternalFormRequestModel(
        m8f_tenant_id=tenant_id,
        reference_id=f"ref-{tenant_id}-{status}-{created_at}-{notified_at}",
        process_instance_id=901,
        task_guid="task-guid-1",
        recipient_user_id=1,
        email="recipient@example.test",
        external_form_url="https://forms.example/f1",
        status=status,
        expires_at_in_seconds=None,
        attempts=0,
        notified_at_in_seconds=notified_at,
        created_at=datetime.fromtimestamp(created_at, timezone.utc),
        updated_at=datetime.fromtimestamp(created_at, timezone.utc),
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_notify_parks_a_request_when_the_tenant_has_no_smtp(app, db_session):
    """The bug this prevents: the sweep re-picked the row every 60s until attempts ran
    out, burning the retry budget on a configuration that cannot succeed."""
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    row = _request_row(db_session)

    with app.app_context():
        g.db_session = db_session
        token = set_context_tenant_id(TENANT)
        try:
            result = ExternalFormNotificationService.notify(row.reference_id)
        finally:
            reset_context_tenant_id(token)

    assert result == "skipped:smtp_unconfigured"
    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.smtp_unconfigured.value
    assert "Missing required secrets" in (row.last_error or "")
    assert row.updated_at is not None
    assert row.updated_at != datetime.fromtimestamp(0, timezone.utc)


def test_atomic_claim_and_release_refresh_native_updated_at(app, db_session, monkeypatch):
    row = _request_row(db_session)
    initial_updated_at = row.updated_at

    monkeypatch.setattr(notification_service.time, "time", lambda: 1_800_000_000)
    with app.app_context():
        g.db_session = db_session
        assert ExternalFormNotificationService.claim(row.id) is True

    db_session.expire_all()
    claimed_updated_at = row.updated_at
    assert claimed_updated_at is not None
    assert claimed_updated_at != initial_updated_at

    monkeypatch.setattr(notification_service.time, "time", lambda: 1_800_000_001)
    with app.app_context():
        g.db_session = db_session
        ExternalFormNotificationService.release_failed(row.id, "SMTP unavailable")

    db_session.expire_all()
    assert row.updated_at is not None
    assert row.updated_at != claimed_updated_at


def test_notify_uses_the_rows_tenant_not_the_ambient_context(app, db_session, _tenant_smtp_secrets, monkeypatch):
    """A context/row tenant mismatch must never pick another tenant's SMTP config."""
    row = _request_row(db_session)
    sent_with = []
    monkeypatch.setattr(
        ExternalFormNotificationService, "send_email", staticmethod(lambda settings, *_: sent_with.append(settings))
    )

    with app.app_context():
        g.db_session = db_session
        token = set_context_tenant_id("other-tenant")
        try:
            result = ExternalFormNotificationService.notify(row.reference_id)
        finally:
            reset_context_tenant_id(token)

    assert result == "sent"
    assert [settings["host"] for settings in sent_with] == ["smtp.example.test"]


def test_sweep_ignores_parked_requests(app, db_session):
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    parked = _request_row(db_session, status=ExternalFormRequestStatus.smtp_unconfigured.value)

    with app.app_context():
        g.db_session = db_session
        candidates = ExternalFormNotificationService.sweep_candidates(now=10_000_000)

    assert parked.reference_id not in {reference_id for _id, reference_id, _tenant in candidates}


def test_revive_returns_parked_requests_to_the_queue(app, db_session, _tenant_smtp_secrets):
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    row = _request_row(db_session, status=ExternalFormRequestStatus.smtp_unconfigured.value)
    row.attempts = 3
    row.last_error = "old failure"
    db_session.commit()

    with app.app_context():
        g.db_session = db_session
        revived = ExternalFormNotificationService.revive_smtp_unconfigured(tenant_id=TENANT)

    assert revived == 1
    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.pending.value
    assert row.attempts == 0
    assert row.last_error is None
    assert row.updated_at is not None
    assert row.updated_at != datetime.fromtimestamp(0, timezone.utc)


def test_revive_does_not_cross_tenants(app, db_session):
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    parked = ExternalFormRequestStatus.smtp_unconfigured.value
    mine = _request_row(db_session, status=parked)
    theirs = _request_row(db_session, tenant_id="other-tenant", status=parked)

    with app.app_context():
        g.db_session = db_session
        ExternalFormNotificationService.revive_smtp_unconfigured(tenant_id=TENANT)

    db_session.expire_all()
    assert mine.status == ExternalFormRequestStatus.pending.value
    assert theirs.status == parked


def test_smtp_configuration_status_reports_keys_never_values(app, _tenant_smtp_secrets):
    with app.app_context():
        status = ExternalFormNotificationService.smtp_configuration_status(TENANT)

    assert status["configured"] is True
    assert status["missing_required_keys"] == []
    assert "NATS_SMTP_HOST" in status["configured_keys"]
    serialized = repr(status)
    assert "smtp.example.test" not in serialized
    assert "noreply@example.test" not in serialized


def test_smtp_configuration_status_names_missing_required_keys(app, db_session):
    with app.app_context():
        status = ExternalFormNotificationService.smtp_configuration_status("tenant-without-smtp")

    assert status["configured"] is False
    assert set(status["missing_required_keys"]) == {"NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"}
    assert "Missing required secrets" in status["reason"]


def test_tenants_with_parked_requests_lists_each_tenant_once(app, db_session):
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    parked = ExternalFormRequestStatus.smtp_unconfigured.value
    _request_row(db_session, status=parked, created_at=1)
    _request_row(db_session, status=parked, created_at=2)
    _request_row(db_session, tenant_id="other-tenant", status=parked)

    with app.app_context():
        g.db_session = db_session
        tenants = ExternalFormNotificationService.tenants_with_parked_requests()

    assert sorted(tenants) == ["other-tenant", TENANT]


# ---------------------------------------------------------------------------
# M8F-575 issue 2: the claim wrote 'notified' before the SMTP send, so a worker
# killed mid-send left a row that looked delivered: the sweep skipped it and resend
# answered 409. A claim is now 'sending' until the send returns, and a claim older
# than the lease belongs to a dead worker and is reclaimed by the sweep.
# ---------------------------------------------------------------------------


def test_a_claimed_request_is_sending_until_the_email_goes_out(app, db_session, _tenant_smtp_secrets, monkeypatch):
    from m8flow_backend.models.external_form_request import ExternalFormRequestModel, ExternalFormRequestStatus

    row = _request_row(db_session)
    status_during_send = []

    def _send(*_args):
        status_during_send.append(db_session.query(ExternalFormRequestModel.status).filter_by(id=row.id).scalar())

    monkeypatch.setattr(ExternalFormNotificationService, "send_email", staticmethod(_send))
    with app.app_context():
        g.db_session = db_session
        token = set_context_tenant_id(TENANT)
        try:
            assert ExternalFormNotificationService.notify(row.reference_id) == "sent"
        finally:
            reset_context_tenant_id(token)

    assert status_during_send == [ExternalFormRequestStatus.sending.value]
    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.notified.value


def test_a_send_interrupted_by_a_worker_crash_is_swept_and_reclaimed(app, db_session, monkeypatch):
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    sending = ExternalFormRequestStatus.sending.value
    lease = notification_service.SEND_LEASE_SECONDS
    crashed = _request_row(db_session, status=sending, notified_at=1_000)
    in_flight = _request_row(db_session, status=sending, notified_at=1_000 + lease, created_at=1)
    now = 1_000 + lease + 1

    with app.app_context():
        g.db_session = db_session
        candidates = ExternalFormNotificationService.sweep_candidates(now=now)
        monkeypatch.setattr(notification_service.time, "time", lambda: now)
        assert ExternalFormNotificationService.claim(crashed.id) is True
        assert ExternalFormNotificationService.claim(in_flight.id) is False

    assert [request_id for request_id, _reference, _tenant in candidates] == [crashed.id]


def test_a_failed_send_releases_the_claim_for_retry(app, db_session):
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    row = _request_row(db_session)
    with app.app_context():
        g.db_session = db_session
        assert ExternalFormNotificationService.claim(row.id) is True
        ExternalFormNotificationService.release_failed(row.id, "SMTP unavailable")

    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.failed.value
    assert row.notified_at_in_seconds is None


def test_a_stale_send_is_parked_when_the_tenant_lost_its_smtp(app, db_session):
    """Otherwise every sweep would re-pick the stuck row and never park or send it."""
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    row = _request_row(db_session, status=ExternalFormRequestStatus.sending.value, notified_at=1)

    with app.app_context():
        g.db_session = db_session
        assert ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no SMTP") == 1

    db_session.expire_all()
    assert (row.status, row.notified_at_in_seconds) == (ExternalFormRequestStatus.smtp_unconfigured.value, None)


def test_notify_retires_a_request_whose_task_has_closed(app, db_session, _tenant_smtp_secrets, monkeypatch):
    """M8F-575 issue 3: never email a link for a task that can no longer be completed."""
    from m8flow_bpmn_core.models.human_task import HumanTaskModel
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    row = _request_row(db_session)
    db_session.add(
        HumanTaskModel(
            id=9601,
            m8f_tenant_id=TENANT,
            process_instance_id=row.process_instance_id,
            task_id=row.task_guid,
            task_name="ExternalForm",
            task_title="Fill form",
            task_type="UserTask",
            task_status="TERMINATED",
            process_model_display_name="Demo",
            bpmn_process_identifier="demo/external",
            completed=True,
        )
    )
    db_session.commit()
    sent = []
    monkeypatch.setattr(ExternalFormNotificationService, "send_email", staticmethod(lambda *args: sent.append(args)))

    with app.app_context():
        g.db_session = db_session
        token = set_context_tenant_id(TENANT)
        try:
            assert ExternalFormNotificationService.notify(row.reference_id) == "skipped:task_closed"
        finally:
            reset_context_tenant_id(token)

    assert sent == []
    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.cancelled.value
