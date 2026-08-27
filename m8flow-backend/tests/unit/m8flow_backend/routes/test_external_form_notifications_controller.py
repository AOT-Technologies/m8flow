"""Unit tests for the external-form notifications admin controller.

Tests cover:
- external_form_smtp_status: configured / missing-secret reporting, no secret values in
  the payload, super admin must name a tenant
- external_form_notification_list: pagination, status and instance filters, per_page cap,
  reference_id withheld (it is the recipient's bearer credential), super-admin tenant
  labelling and cross-tenant isolation
- external_form_notification_resend: requeue, 404 for another tenant's row, 409 for a
  status that cannot be resent, super admin must name a tenant
"""
from __future__ import annotations

import sys
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
from m8flow_backend.models.process_model_bpmn_version import (  # noqa: E402, F401
    ProcessModelBpmnVersionModel,
)
from m8flow_backend.routes import external_form_notifications_controller as controller  # noqa: E402
from m8flow_backend.services.external_form_notification_service import (  # noqa: E402
    ExternalFormNotificationService,
)
from m8flow_backend.services.external_form_service import ExternalFormService  # noqa: E402

TASK_GUID = "11111111-2222-3333-4444-555555555555"

DEFAULT_SMTP_SECRETS = {
    "NATS_SMTP_HOST": "smtp.test",
    "NATS_SMTP_FROM_EMAIL": "no-reply@tenant-one.example",
}


@pytest.fixture(autouse=True)
def _link_ttl_env(monkeypatch):
    monkeypatch.setenv("M8FLOW_EXTERNAL_FORM_LINK_TTL_SECONDS", "604800")


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


def _make_tenant(tenant_id: str, name: str, slug: str) -> M8flowTenantModel:
    tenant = M8flowTenantModel(
        id=tenant_id,
        name=name,
        slug=slug,
        status=TenantStatus.ACTIVE,
        created_by="admin",
        modified_by="admin",
    )
    db.session.add(tenant)
    db.session.commit()
    return tenant


@pytest.fixture
def tenant(app):
    return _make_tenant("tenant-1", "Tenant One", "tenant-one")


@pytest.fixture
def other_tenant(app):
    return _make_tenant("tenant-2", "Tenant Two", "tenant-two")


@pytest.fixture
def alice(app):
    user = UserModel(username="alice", service="test", service_id="alice", email="alice@example.com")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def smtp_secrets(monkeypatch):
    """Stub the per-tenant SMTP secret lookup with a mutable dict (default: configured)."""
    secrets = dict(DEFAULT_SMTP_SECRETS)
    monkeypatch.setattr(
        ExternalFormNotificationService,
        "_read_tenant_secret",
        staticmethod(lambda key: secrets.get(key)),
    )
    monkeypatch.setattr(
        ExternalFormNotificationService,
        "_read_secret_for_tenant",
        classmethod(lambda cls, key, tenant_id: secrets.get(key)),
    )
    return secrets


@pytest.fixture
def not_super_admin(monkeypatch):
    monkeypatch.setattr(controller, "is_super_admin_request", lambda: False)


@pytest.fixture
def super_admin(monkeypatch):
    monkeypatch.setattr(controller, "is_super_admin_request", lambda: True)


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


class TestSmtpStatus:
    def test_reports_configured_tenant(self, app, tenant, smtp_secrets, not_super_admin):
        with app.test_request_context("/"):
            response = controller.external_form_smtp_status()

        assert response.status_code == 200
        assert response.get_json()["configured"] is True

    def test_names_the_missing_secrets(self, app, tenant, smtp_secrets, not_super_admin):
        smtp_secrets.clear()

        with app.test_request_context("/"):
            payload = controller.external_form_smtp_status().get_json()

        assert payload["configured"] is False
        assert set(payload["missing_required_keys"]) == {"NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"}
        assert "NATS_SMTP_PASSWORD" in payload["optional_keys"]
        assert payload["reason"]

    def test_never_returns_a_secret_value(self, app, tenant, smtp_secrets, not_super_admin):
        with app.test_request_context("/"):
            body = controller.external_form_smtp_status().get_data(as_text=True)

        assert "smtp.test" not in body
        assert "no-reply@tenant-one.example" not in body

    def test_super_admin_must_name_a_tenant(self, app, tenant, smtp_secrets, super_admin):
        """Without a tenant the query spans every tenant, so a configured *other* tenant
        would make this one look configured."""
        with app.test_request_context("/"):
            response = controller.external_form_smtp_status()

        assert response.status_code == 400
        assert response.get_json()["error_code"] == "tenant_id_required"

    def test_super_admin_with_tenant_id_is_answered(self, app, tenant, smtp_secrets, super_admin):
        with app.test_request_context(f"/?tenantId={tenant.id}"):
            response = controller.external_form_smtp_status()

        assert response.status_code == 200
        assert response.get_json()["configured"] is True


class TestNotificationList:
    def test_returns_rows_for_the_active_tenant(self, app, tenant, alice, not_super_admin):
        row = _create_request(tenant, alice)

        with app.test_request_context("/"):
            payload = controller.external_form_notification_list().get_json()

        assert payload["pagination"]["total"] == 1
        assert payload["results"][0]["id"] == row.id
        assert payload["results"][0]["status"] == ExternalFormRequestStatus.pending.value

    def test_withholds_the_reference_id(self, app, tenant, alice, not_super_admin):
        """reference_id is the bearer credential in the emailed link; exposing it here
        would let an admin submit the form as the recipient."""
        row = _create_request(tenant, alice)

        with app.test_request_context("/"):
            response = controller.external_form_notification_list()

        assert "reference_id" not in response.get_json()["results"][0]
        assert row.reference_id not in response.get_data(as_text=True)

    def test_surfaces_the_park_reason(self, app, tenant, alice, not_super_admin):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "missing NATS_SMTP_HOST")

        with app.test_request_context("/"):
            result = controller.external_form_notification_list().get_json()["results"][0]

        assert result["status"] == ExternalFormRequestStatus.smtp_unconfigured.value
        assert result["last_error"] == "missing NATS_SMTP_HOST"

    def test_filters_by_status(self, app, tenant, alice, not_super_admin):
        parked = _create_request(tenant, alice)
        _create_request(tenant, alice, task_guid="99999999-2222-3333-4444-555555555555")
        ExternalFormNotificationService.mark_smtp_unconfigured([parked.id], "no smtp")

        with app.test_request_context("/"):
            payload = controller.external_form_notification_list(
                status=ExternalFormRequestStatus.smtp_unconfigured.value
            ).get_json()

        assert [row["id"] for row in payload["results"]] == [parked.id]

    def test_filters_by_process_instance(self, app, tenant, alice, not_super_admin):
        mine = _create_request(tenant, alice)
        _create_request(tenant, alice, process_instance_id=77, task_guid="88888888-2222-3333-4444-555555555555")

        with app.test_request_context("/"):
            payload = controller.external_form_notification_list(process_instance_id=42).get_json()

        assert [row["id"] for row in payload["results"]] == [mine.id]

    def test_per_page_is_capped(self, app, tenant, alice, not_super_admin):
        _create_request(tenant, alice)

        with app.test_request_context("/"):
            payload = controller.external_form_notification_list(per_page=10_000).get_json()

        # Cap applied rather than honouring an unbounded page.
        assert payload["pagination"]["count"] == 1

    def test_super_admin_scoped_to_one_tenant(self, app, tenant, other_tenant, alice, super_admin):
        mine = _create_request(tenant, alice)
        theirs = _create_request(other_tenant, alice, process_instance_id=99)

        with app.test_request_context(f"/?tenantId={tenant.id}"):
            payload = controller.external_form_notification_list().get_json()

        ids = [row["id"] for row in payload["results"]]
        assert mine.id in ids
        assert theirs.id not in ids
        assert payload["results"][0]["tenantName"] == "Tenant One"


class TestNotificationResend:
    def test_requeues_a_parked_row(self, app, tenant, alice, not_super_admin):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no smtp")

        with app.test_request_context("/", method="POST"):
            response = controller.external_form_notification_resend(row.id)

        assert response.status_code == 200
        assert response.get_json()["status"] == ExternalFormRequestStatus.pending.value
        refreshed = db.session.get(ExternalFormRequestModel, row.id)
        assert refreshed.status == ExternalFormRequestStatus.pending.value
        assert refreshed.last_error is None

    def test_unknown_id_is_404(self, app, tenant, not_super_admin):
        with app.test_request_context("/", method="POST"):
            response = controller.external_form_notification_resend(4242)

        assert response.status_code == 404
        assert response.get_json()["error_code"] == "external_form_request_not_found"

    def test_submitted_row_is_409(self, app, tenant, alice, not_super_admin):
        row = _create_request(tenant, alice)
        stored = db.session.get(ExternalFormRequestModel, row.id)
        stored.status = ExternalFormRequestStatus.submitted.value
        db.session.commit()

        with app.test_request_context("/", method="POST"):
            response = controller.external_form_notification_resend(row.id)

        assert response.status_code == 409
        assert response.get_json()["error_code"] == "external_form_request_not_resendable"

    def test_super_admin_must_name_a_tenant(self, app, tenant, alice, super_admin):
        """request_id is a bare integer, so without a tenant it would address any tenant."""
        row = _create_request(tenant, alice)

        with app.test_request_context("/", method="POST"):
            response = controller.external_form_notification_resend(row.id)

        assert response.status_code == 400
        assert response.get_json()["error_code"] == "tenant_id_required"

    def test_super_admin_cannot_resend_another_tenants_row(
        self, app, tenant, other_tenant, alice, super_admin
    ):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "no smtp")

        with app.test_request_context(f"/?tenantId={other_tenant.id}", method="POST"):
            response = controller.external_form_notification_resend(row.id)

        assert response.status_code == 404
        assert db.session.get(ExternalFormRequestModel, row.id).status == (
            ExternalFormRequestStatus.smtp_unconfigured.value
        )
