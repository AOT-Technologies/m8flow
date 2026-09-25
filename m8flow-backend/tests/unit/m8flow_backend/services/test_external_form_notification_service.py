"""Tenant resolution for the notification worker's SMTP lookup.

The worker runs outside any request context and sets the active tenant in the
ContextVar (`set_context_tenant_id`), so a `g`-only read of the tenant id found
nothing and every send reported `skipped:smtp_unconfigured` -- the tenant's
NATS_SMTP_* secrets were configured and still never used. These tests pin the
`get_tenant_id()` resolution, exercising both the worker's non-request shape and
the request shape a route provides.
"""

from __future__ import annotations

import pytest
from flask import g

from m8flow_backend.auth.tenant_context import reset_context_tenant_id, set_context_tenant_id
from m8flow_backend.secrets import add_secret
from m8flow_backend.services.external_form_notification_service import (
    ExternalFormNotificationService,
)

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
        created_at_in_seconds=created_at,
        updated_at_in_seconds=created_at,
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


def test_requeue_moves_a_parked_request(app, db_session):
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    row = _request_row(db_session, status=ExternalFormRequestStatus.smtp_unconfigured.value)

    with app.app_context():
        g.db_session = db_session
        assert ExternalFormNotificationService.requeue(row.id, tenant_id=TENANT) is True

    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.pending.value


def test_requeue_refuses_a_completed_request(app, db_session):
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    row = _request_row(db_session, status=ExternalFormRequestStatus.completed.value)

    with app.app_context():
        g.db_session = db_session
        assert ExternalFormNotificationService.requeue(row.id, tenant_id=TENANT) is False

    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.completed.value


def test_requeue_refuses_a_failed_resume(app, db_session):
    """`failed` with notified_at still set means the email went out and the workflow
    resume failed -- re-emailing that link would be wrong."""
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    row = _request_row(
        db_session, status=ExternalFormRequestStatus.failed.value, notified_at=1_700_000_000
    )

    with app.app_context():
        g.db_session = db_session
        assert ExternalFormNotificationService.requeue(row.id, tenant_id=TENANT) is False


def test_requeue_does_not_cross_tenants(app, db_session):
    from m8flow_backend.models.external_form_request import ExternalFormRequestStatus

    row = _request_row(
        db_session, tenant_id="other-tenant", status=ExternalFormRequestStatus.smtp_unconfigured.value
    )

    with app.app_context():
        g.db_session = db_session
        assert ExternalFormNotificationService.requeue(row.id, tenant_id=TENANT) is False


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
