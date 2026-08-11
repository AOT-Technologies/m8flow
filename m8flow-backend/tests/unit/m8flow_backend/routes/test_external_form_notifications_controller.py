"""Unit tests for external_form_notifications_controller.

Tests cover:
- smtp-status response shape: key names and flags only, never a secret value
- list response: pagination shape, filters, and the reference_id exclusion that keeps the
  emailed link's bearer token out of an admin-readable endpoint
- resend: 200 on requeue, 404 for a foreign/unknown id, 409 for a non-resendable status
- super-admin tenant scoping: these requests are exempt from the tenant-scoping query
  listener, so every handler must apply an explicit tenant filter of its own
- api.yml + permissions wiring
"""
import sys
from pathlib import Path

import pytest
from flask import Flask, g

# Setup path for imports
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

# Install the model overrides before any spiff model is touched: these tests write and
# filter SecretModel rows by m8f_tenant_id, which only exists on the m8flow override.
# Idempotent — the repo conftest's bootstrap() has normally already done this.
from m8flow_backend.services.model_override_patch import apply as apply_model_overrides  # noqa: E402

apply_model_overrides()

from spiffworkflow_backend.models.db import add_listeners, db  # noqa: E402
# Registers the `secret` table before db.create_all(); smtp_configuration_status()
# presence-checks optional keys against it.
from spiffworkflow_backend.models.secret_model import SecretModel  # noqa: E402,F401
from spiffworkflow_backend.models.user import UserModel  # noqa: E402

from m8flow_backend.models.external_form_request import (  # noqa: E402
    ExternalFormRequestModel,
    ExternalFormRequestStatus,
)
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from m8flow_backend.routes import external_form_notifications_controller as controller  # noqa: E402
from m8flow_backend.services.external_form_notification_service import (  # noqa: E402
    ExternalFormNotificationService,
)
from m8flow_backend.services.external_form_service import ExternalFormService  # noqa: E402

TASK_GUID = "11111111-2222-3333-4444-555555555555"

SMTP_SECRETS = {
    "NATS_SMTP_HOST": "smtp.test",
    "NATS_SMTP_FROM_EMAIL": "no-reply@tenant-one.example",
}


@pytest.fixture(autouse=True)
def _notification_env(monkeypatch):
    monkeypatch.setenv("M8FLOW_EXTERNAL_FORM_LINK_TTL_SECONDS", "604800")


@pytest.fixture
def smtp_secrets(monkeypatch):
    secrets = dict(SMTP_SECRETS)
    monkeypatch.setattr(
        ExternalFormNotificationService,
        "_read_tenant_secret",
        staticmethod(lambda key: secrets.get(key)),
    )
    return secrets


class ReversibleCipher:
    """Stand-in for the configured CIPHER. Reversible and trivial: these tests are about
    tenant scoping, not cryptography."""

    @staticmethod
    def encrypt(value):
        if isinstance(value, bytes):
            value = value.decode("ascii")
        return f"enc:{value}".encode("ascii")

    @staticmethod
    def decrypt(value):
        return value.decode("ascii").removeprefix("enc:").encode("ascii")


@pytest.fixture
def app():
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    app.config["CIPHER"] = ReversibleCipher()
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


def _add_secret(tenant_id: str, key: str, value: str, user_id: int) -> None:
    """Write a real (encrypted) secret row for a specific tenant.

    Written directly rather than via SecretService.add_secret so the owning tenant is
    explicit — the scoping listener does not stamp it during these bare-app tests."""
    from spiffworkflow_backend.services.secret_service import SecretService

    db.session.add(
        SecretModel(
            key=key,
            value=SecretService._encrypt(value),
            user_id=user_id,
            m8f_tenant_id=tenant_id,
        )
    )
    db.session.commit()


@pytest.fixture
def alice(app):
    user = UserModel(username="alice", service="test", service_id="alice", email="alice@example.com")
    db.session.add(user)
    db.session.commit()
    return user


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
    def test_reports_configured_without_leaking_values(self, app, tenant, smtp_secrets):
        with app.test_request_context("/m8flow/external-form-notifications/smtp-status"):
            response = controller.external_form_smtp_status()

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["configured"] is True
        assert payload["required_keys"] == ["NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"]
        body = response.get_data(as_text=True)
        for value in SMTP_SECRETS.values():
            assert value not in body

    def test_reports_missing_required_keys(self, app, tenant, smtp_secrets):
        smtp_secrets.clear()

        with app.test_request_context("/m8flow/external-form-notifications/smtp-status"):
            response = controller.external_form_smtp_status()

        payload = response.get_json()
        assert payload["configured"] is False
        assert payload["missing_required_keys"] == ["NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"]
        assert [field["secretKey"] for field in payload["fields"]][:2] == [
            "NATS_SMTP_HOST",
            "NATS_SMTP_FROM_EMAIL",
        ]


class TestUnreadableSecrets:
    """A secret that exists but cannot be decrypted blocks sending just like a missing
    one, but re-entering the key is not the fix — so it must not be reported as missing."""

    def test_status_separates_unreadable_from_missing(self, app, tenant, alice, monkeypatch):
        _add_secret(tenant.id, "NATS_SMTP_HOST", "smtp.one", alice.id)
        _add_secret(tenant.id, "NATS_SMTP_FROM_EMAIL", "no-reply@one.example", alice.id)

        class BrokenCipher(ReversibleCipher):
            @staticmethod
            def decrypt(value):
                raise ValueError("bad key")

        monkeypatch.setitem(app.config, "CIPHER", BrokenCipher())

        with app.test_request_context("/m8flow/external-form-notifications/smtp-status"):
            payload = controller.external_form_smtp_status().get_json()

        assert payload["configured"] is False
        assert payload["unreadable_keys"] == ["NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"]
        assert "encryption key" in payload["reason"]
        assert "Missing required secrets" not in payload["reason"]

    def test_absent_secrets_are_reported_as_missing_not_unreadable(self, app, tenant):
        with app.test_request_context("/m8flow/external-form-notifications/smtp-status"):
            payload = controller.external_form_smtp_status().get_json()

        assert payload["unreadable_keys"] == []
        assert "Missing required secrets" in payload["reason"]


class TestNotificationList:
    def test_never_returns_the_reference_id(self, app, tenant, alice):
        """reference_id is the bearer credential in the recipient's emailed link; an admin
        listing must not hand it out."""
        row = _create_request(tenant, alice)

        with app.test_request_context("/m8flow/external-form-notifications"):
            response = controller.external_form_notification_list()

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert row.reference_id not in body
        result = response.get_json()["results"][0]
        assert "reference_id" not in result
        assert result["id"] == row.id
        assert result["email"] == "alice@example.com"
        assert result["status"] == ExternalFormRequestStatus.pending.value

    def test_pagination_shape(self, app, tenant, alice):
        _create_request(tenant, alice)

        with app.test_request_context("/m8flow/external-form-notifications"):
            response = controller.external_form_notification_list(page=1, per_page=10)

        pagination = response.get_json()["pagination"]
        assert pagination["count"] == 1
        assert pagination["total"] == 1
        assert pagination["pages"] == 1

    def test_status_filter(self, app, tenant, alice, smtp_secrets):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "Missing required secrets: NATS_SMTP_HOST")
        _create_request(tenant, alice, task_guid="22222222-2222-3333-4444-555555555555")

        with app.test_request_context("/m8flow/external-form-notifications"):
            response = controller.external_form_notification_list(
                status=ExternalFormRequestStatus.smtp_unconfigured.value
            )

        results = response.get_json()["results"]
        assert [item["id"] for item in results] == [row.id]
        assert "NATS_SMTP_HOST" in results[0]["last_error"]

    def test_process_instance_filter(self, app, tenant, alice):
        _create_request(tenant, alice)
        other = _create_request(
            tenant, alice, process_instance_id=99, task_guid="33333333-2222-3333-4444-555555555555"
        )

        with app.test_request_context("/m8flow/external-form-notifications"):
            response = controller.external_form_notification_list(process_instance_id=99)

        assert [item["id"] for item in response.get_json()["results"]] == [other.id]

    def test_per_page_is_capped(self, app, tenant, alice):
        _create_request(tenant, alice)

        with app.test_request_context("/m8flow/external-form-notifications"):
            response = controller.external_form_notification_list(per_page=100_000)

        assert response.status_code == 200


class TestResend:
    def test_requeues_a_parked_request(self, app, tenant, alice, smtp_secrets):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.mark_smtp_unconfigured([row.id], "Missing required secrets: NATS_SMTP_HOST")

        with app.test_request_context(f"/m8flow/external-form-notifications/{row.id}/resend", method="POST"):
            response = controller.external_form_notification_resend(row.id)

        assert response.status_code == 200
        assert response.get_json()["status"] == ExternalFormRequestStatus.pending.value
        db.session.expire_all()
        assert db.session.get(ExternalFormRequestModel, row.id).status == (
            ExternalFormRequestStatus.pending.value
        )

    def test_unknown_id_is_404(self, app, tenant):
        with app.test_request_context("/m8flow/external-form-notifications/9999/resend", method="POST"):
            response = controller.external_form_notification_resend(9999)

        assert response.status_code == 404
        assert response.get_json()["error_code"] == "external_form_request_not_found"

    def test_already_notified_is_409(self, app, tenant, alice):
        row = _create_request(tenant, alice)
        ExternalFormNotificationService.claim(row.id)

        with app.test_request_context(f"/m8flow/external-form-notifications/{row.id}/resend", method="POST"):
            response = controller.external_form_notification_resend(row.id)

        assert response.status_code == 409
        assert response.get_json()["error_code"] == "external_form_request_not_resendable"


class TestSuperAdminTenantScoping:
    """Super-admin requests are exempt from the tenant-scoping query listener (see
    tenant_scoping_patch._tenant_scope_queries), so each handler must scope itself.
    Without that, a super admin reads another tenant's secrets and rows."""

    def _super_admin_context(self, app, path):
        context = app.test_request_context(path)
        context.push()
        g._m8flow_super_admin_request = True
        return context

    def test_smtp_status_requires_a_tenant(self, app, tenant):
        context = self._super_admin_context(app, "/m8flow/external-form-notifications/smtp-status")
        try:
            response = controller.external_form_smtp_status()
        finally:
            context.pop()

        assert response.status_code == 400
        assert response.get_json()["error_code"] == "tenant_id_required"

    def test_smtp_status_does_not_borrow_another_tenants_secrets(
        self, app, tenant, other_tenant, alice
    ):
        # Only tenant-2 has SMTP configured.
        _add_secret(other_tenant.id, "NATS_SMTP_HOST", "smtp.two", alice.id)
        _add_secret(other_tenant.id, "NATS_SMTP_FROM_EMAIL", "no-reply@two.example", alice.id)

        context = self._super_admin_context(
            app, f"/m8flow/external-form-notifications/smtp-status?tenantId={tenant.id}"
        )
        try:
            response = controller.external_form_smtp_status()
        finally:
            context.pop()

        payload = response.get_json()
        assert payload["configured"] is False
        assert payload["missing_required_keys"] == ["NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"]

    def test_smtp_status_reports_the_named_tenant(self, app, tenant, other_tenant, alice):
        _add_secret(tenant.id, "NATS_SMTP_HOST", "smtp.one", alice.id)
        _add_secret(tenant.id, "NATS_SMTP_FROM_EMAIL", "no-reply@one.example", alice.id)

        context = self._super_admin_context(
            app, f"/m8flow/external-form-notifications/smtp-status?tenantId={tenant.id}"
        )
        try:
            response = controller.external_form_smtp_status()
        finally:
            context.pop()

        payload = response.get_json()
        assert payload["configured"] is True
        assert "smtp.one" not in response.get_data(as_text=True)

    def test_list_restricts_to_the_named_tenant_and_labels_rows(
        self, app, tenant, other_tenant, alice
    ):
        mine = _create_request(tenant, alice)
        _create_request(other_tenant, alice, task_guid="44444444-2222-3333-4444-555555555555")

        context = self._super_admin_context(
            app, f"/m8flow/external-form-notifications?tenantId={tenant.id}"
        )
        try:
            response = controller.external_form_notification_list()
        finally:
            context.pop()

        results = response.get_json()["results"]
        assert [item["id"] for item in results] == [mine.id]
        assert results[0]["tenantId"] == tenant.id
        assert results[0]["tenantName"] == "Tenant One"

    def test_list_without_a_tenant_labels_every_row(self, app, tenant, other_tenant, alice):
        """Recipient email addresses are in this payload, so a cross-tenant view must at
        least attribute each row rather than return an unlabelled mix."""
        _create_request(tenant, alice)
        _create_request(other_tenant, alice, task_guid="55555555-2222-3333-4444-555555555555")

        context = self._super_admin_context(app, "/m8flow/external-form-notifications")
        try:
            response = controller.external_form_notification_list()
        finally:
            context.pop()

        results = response.get_json()["results"]
        assert len(results) == 2
        assert {item["tenantId"] for item in results} == {tenant.id, other_tenant.id}

    def test_resend_requires_a_tenant(self, app, tenant, alice):
        row = _create_request(tenant, alice)

        context = self._super_admin_context(
            app, f"/m8flow/external-form-notifications/{row.id}/resend"
        )
        try:
            response = controller.external_form_notification_resend(row.id)
        finally:
            context.pop()

        assert response.status_code == 400
        assert response.get_json()["error_code"] == "tenant_id_required"

    def test_resend_cannot_reach_another_tenants_row(self, app, tenant, other_tenant, alice):
        foreign = _create_request(other_tenant, alice)

        context = self._super_admin_context(
            app, f"/m8flow/external-form-notifications/{foreign.id}/resend?tenantId={tenant.id}"
        )
        try:
            response = controller.external_form_notification_resend(foreign.id)
        finally:
            context.pop()

        assert response.status_code == 404
        db.session.expire_all()
        assert db.session.get(ExternalFormRequestModel, foreign.id).status == (
            ExternalFormRequestStatus.pending.value
        )

    def test_ordinary_request_ignores_a_tenant_id_param(self, app, tenant, other_tenant, alice):
        """A normal user is scoped by the listener; honouring their ?tenantId= would be a
        way to name someone else's tenant, so the param must be inert for them."""
        row = _create_request(tenant, alice)

        with app.test_request_context(
            f"/m8flow/external-form-notifications?tenantId={other_tenant.id}"
        ):
            response = controller.external_form_notification_list()

        results = response.get_json()["results"]
        assert [item["id"] for item in results] == [row.id]
        assert "tenantId" not in results[0]


class TestWiring:
    def test_api_yml_declares_the_routes(self):
        import yaml

        spec = yaml.safe_load((extension_root / "src" / "m8flow_backend" / "api.yml").read_text())
        paths = spec["paths"]

        prefix = "m8flow_backend.routes.external_form_notifications_controller"
        assert (
            paths["/external-form-notifications/smtp-status"]["get"]["operationId"]
            == f"{prefix}.external_form_smtp_status"
        )
        assert (
            paths["/external-form-notifications"]["get"]["operationId"]
            == f"{prefix}.external_form_notification_list"
        )
        assert (
            paths["/external-form-notifications/{request_id}/resend"]["post"]["operationId"]
            == f"{prefix}.external_form_notification_resend"
        )

    def test_routes_are_not_publicly_accessible(self):
        """These endpoints expose tenant configuration and recipient addresses, so unlike
        the recipient-facing /external-forms routes they must keep the default security."""
        import yaml

        spec = yaml.safe_load((extension_root / "src" / "m8flow_backend" / "api.yml").read_text())
        for path in (
            "/external-form-notifications/smtp-status",
            "/external-form-notifications",
            "/external-form-notifications/{request_id}/resend",
        ):
            for operation in spec["paths"][path].values():
                assert "security" not in operation

    def test_permissions_are_declared(self):
        import yaml

        permissions_yml = (
            extension_root / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
        )
        permissions = yaml.safe_load(permissions_yml.read_text())["permissions"]

        smtp_status = permissions["read-external-form-smtp-status"]
        assert smtp_status["uri"] == "/m8flow/external-form-notifications/smtp-status"
        # Editors see the modeler warning, so they need to read the status.
        assert "editor" in smtp_status["groups"]

        listing = permissions["read-external-form-notifications"]
        assert listing["uri"] == "/m8flow/external-form-notifications"
        # Recipient email addresses are admin-only.
        assert "editor" not in listing["groups"]
        assert set(listing["groups"]) == {"tenant-admin", "super-admin"}

        resend = permissions["resend-external-form-notifications"]
        assert resend["actions"] == ["create"]
        assert set(resend["groups"]) == {"tenant-admin", "super-admin"}
