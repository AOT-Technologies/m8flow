"""Unit tests for ExternalFormService (M8F-338).

Tests cover:
- create_requests_for_task: one PENDING row per recipient, default expiry,
  duplicate-skip on event redelivery
- get_form_context: unknown reference, actionable flag, lazy expiry
- submit: validation matrix (unknown / already-submitted / superseded / expired),
  first-submit-wins with sibling supersede, workflow resume as recipient user,
  failure recording (status failed, attempts, last_error) and retry
"""
import sys
import time
from pathlib import Path
from unittest.mock import Mock

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

from spiffworkflow_backend.exceptions.api_error import ApiError  # noqa: E402
from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.models.db import add_listeners  # noqa: E402
from spiffworkflow_backend.models.user import UserModel  # noqa: E402

from m8flow_backend.models.external_form_request import (  # noqa: E402
    ExternalFormRequestModel,
    ExternalFormRequestStatus,
)
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from m8flow_backend.services.external_form_service import ExternalFormService  # noqa: E402
from m8flow_backend.tenancy import get_context_tenant_id  # noqa: E402

TASK_GUID = "11111111-2222-3333-4444-555555555555"


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


@pytest.fixture
def bob(app):
    user = UserModel(username="bob", service="test", service_id="bob", email="bob@example.com")
    db.session.add(user)
    db.session.commit()
    return user


def _create_requests(tenant, *users, **kwargs):
    defaults = {
        "tenant_id": tenant.id,
        "process_instance_id": 42,
        "task_guid": TASK_GUID,
        "external_form_url": "https://forms.example.com/leave-request",
        "recipients": [{"user_id": u.id, "email": u.email, "user_details": {"username": u.username}} for u in users],
    }
    defaults.update(kwargs)
    return ExternalFormService.create_requests_for_task(**defaults)


class TestCreateRequestsForTask:
    def test_creates_one_pending_row_per_recipient(self, app, tenant, alice, bob):
        rows = _create_requests(tenant, alice, bob)

        assert len(rows) == 2
        assert {r.recipient_user_id for r in rows} == {alice.id, bob.id}
        for row in rows:
            assert row.status == ExternalFormRequestStatus.pending.value
            assert row.m8f_tenant_id == tenant.id
            assert row.expires_at_in_seconds > int(time.time())
        assert rows[0].reference_id != rows[1].reference_id

    def test_skips_recipients_with_existing_actionable_row(self, app, tenant, alice, bob):
        _create_requests(tenant, alice)

        rows = _create_requests(tenant, alice, bob)
        assert len(rows) == 1
        assert rows[0].recipient_user_id == bob.id
        assert ExternalFormRequestModel.query.filter_by(recipient_user_id=alice.id).count() == 1

    def test_recreates_for_recipient_whose_row_is_terminal(self, app, tenant, alice):
        (first,) = _create_requests(tenant, alice)
        first.status = ExternalFormRequestStatus.superseded.value
        db.session.commit()

        rows = _create_requests(tenant, alice)
        assert len(rows) == 1

    def test_explicit_expiry_is_used(self, app, tenant, alice):
        (row,) = _create_requests(tenant, alice, expires_at_in_seconds=1234567890)
        assert row.expires_at_in_seconds == 1234567890


class TestGetFormContext:
    def test_unknown_reference_raises_404(self, app):
        with pytest.raises(ApiError) as exc_info:
            ExternalFormService.get_form_context("nope")
        assert exc_info.value.error_code == "invalid_reference_id"
        assert exc_info.value.status_code == 404

    def test_actionable_link_returns_context(self, app, tenant, alice):
        (row,) = _create_requests(tenant, alice)

        with app.test_request_context():
            context = ExternalFormService.get_form_context(row.reference_id)

        assert context["actionable"] is True
        assert context["status"] == ExternalFormRequestStatus.pending.value
        assert context["external_form_url"] == "https://forms.example.com/leave-request"
        assert context["process_instance_id"] == 42

    def test_expired_link_is_lazily_marked_and_not_actionable(self, app, tenant, alice):
        (row,) = _create_requests(tenant, alice, expires_at_in_seconds=int(time.time()) - 10)

        with app.test_request_context():
            context = ExternalFormService.get_form_context(row.reference_id)

        assert context["actionable"] is False
        assert context["status"] == ExternalFormRequestStatus.expired.value
        assert ExternalFormRequestModel.query.filter_by(id=row.id).first().status == (
            ExternalFormRequestStatus.expired.value
        )

    def test_sets_tenant_context_from_row(self, app, tenant, alice):
        (row,) = _create_requests(tenant, alice)

        with app.test_request_context():
            ExternalFormService.get_form_context(row.reference_id)
            assert g.m8flow_tenant_id == tenant.id
            assert get_context_tenant_id() == tenant.id


class TestSubmit:
    def test_unknown_reference_raises_404(self, app):
        with pytest.raises(ApiError) as exc_info:
            ExternalFormService.submit("nope", {"a": 1})
        assert exc_info.value.status_code == 404

    def test_happy_path_completes_task_as_recipient_and_supersedes_siblings(
        self, app, tenant, alice, bob, monkeypatch
    ):
        alice_row, bob_row = _create_requests(tenant, alice, bob)

        task_submit_mock = Mock(return_value={})
        monkeypatch.setattr(
            "spiffworkflow_backend.routes.process_api_blueprint._task_submit_shared", task_submit_mock
        )

        with app.test_request_context():
            result = ExternalFormService.submit(alice_row.reference_id, {"answer": 42})
            assert g.user.id == alice.id
            assert g.m8flow_tenant_id == tenant.id

        task_submit_mock.assert_called_once_with(42, TASK_GUID, {"answer": 42})
        assert result["status"] == ExternalFormRequestStatus.completed.value
        assert alice_row.status == ExternalFormRequestStatus.completed.value
        assert alice_row.form_submission_data == {"answer": 42}
        assert bob_row.status == ExternalFormRequestStatus.superseded.value

    def test_repeated_submit_is_rejected_with_409(self, app, tenant, alice, monkeypatch):
        (row,) = _create_requests(tenant, alice)
        monkeypatch.setattr(
            "spiffworkflow_backend.routes.process_api_blueprint._task_submit_shared", Mock(return_value={})
        )

        with app.test_request_context():
            ExternalFormService.submit(row.reference_id, {"answer": 1})

            with pytest.raises(ApiError) as exc_info:
                ExternalFormService.submit(row.reference_id, {"answer": 2})

        assert exc_info.value.error_code == "already_submitted"
        assert exc_info.value.status_code == 409
        assert row.form_submission_data == {"answer": 1}

    def test_superseded_link_is_rejected_with_410(self, app, tenant, alice, bob, monkeypatch):
        alice_row, bob_row = _create_requests(tenant, alice, bob)
        monkeypatch.setattr(
            "spiffworkflow_backend.routes.process_api_blueprint._task_submit_shared", Mock(return_value={})
        )

        with app.test_request_context():
            ExternalFormService.submit(alice_row.reference_id, {"answer": 1})

            with pytest.raises(ApiError) as exc_info:
                ExternalFormService.submit(bob_row.reference_id, {"answer": 2})

        assert exc_info.value.error_code == "reference_superseded"
        assert exc_info.value.status_code == 410

    def test_expired_link_is_rejected_with_410(self, app, tenant, alice):
        (row,) = _create_requests(tenant, alice, expires_at_in_seconds=int(time.time()) - 10)

        with app.test_request_context():
            with pytest.raises(ApiError) as exc_info:
                ExternalFormService.submit(row.reference_id, {"answer": 1})

        assert exc_info.value.error_code == "reference_expired"
        assert exc_info.value.status_code == 410
        assert row.status == ExternalFormRequestStatus.expired.value

    def test_engine_api_error_records_failure_and_keeps_link_retryable(self, app, tenant, alice, monkeypatch):
        (row,) = _create_requests(tenant, alice)
        monkeypatch.setattr(
            "spiffworkflow_backend.routes.process_api_blueprint._task_submit_shared",
            Mock(side_effect=ApiError(error_code="invalid_state", message="not READY", status_code=400)),
        )

        with app.test_request_context():
            with pytest.raises(ApiError) as exc_info:
                ExternalFormService.submit(row.reference_id, {"answer": 1})

        assert exc_info.value.error_code == "invalid_state"
        assert row.status == ExternalFormRequestStatus.failed.value
        assert row.attempts == 1
        assert "invalid_state" in row.last_error
        assert row.is_actionable()

    def test_unexpected_engine_error_is_wrapped_and_recorded(self, app, tenant, alice, monkeypatch):
        (row,) = _create_requests(tenant, alice)
        monkeypatch.setattr(
            "spiffworkflow_backend.routes.process_api_blueprint._task_submit_shared",
            Mock(side_effect=RuntimeError("boom")),
        )

        with app.test_request_context():
            with pytest.raises(ApiError) as exc_info:
                ExternalFormService.submit(row.reference_id, {"answer": 1})

        assert exc_info.value.error_code == "workflow_resume_failed"
        assert exc_info.value.status_code == 500
        assert row.status == ExternalFormRequestStatus.failed.value
        assert "boom" in row.last_error

    def test_failed_link_can_be_retried_successfully(self, app, tenant, alice, monkeypatch):
        (row,) = _create_requests(tenant, alice)
        monkeypatch.setattr(
            "spiffworkflow_backend.routes.process_api_blueprint._task_submit_shared",
            Mock(side_effect=[RuntimeError("boom"), {}]),
        )

        with app.test_request_context():
            with pytest.raises(ApiError):
                ExternalFormService.submit(row.reference_id, {"answer": 1})
            result = ExternalFormService.submit(row.reference_id, {"answer": 2})

        assert result["status"] == ExternalFormRequestStatus.completed.value
        assert row.form_submission_data == {"answer": 2}

    def test_missing_recipient_user_is_rejected_with_410(self, app, tenant, alice):
        (row,) = _create_requests(tenant, alice)
        row.recipient_user_id = 99999
        db.session.commit()

        with app.test_request_context():
            with pytest.raises(ApiError) as exc_info:
                ExternalFormService.submit(row.reference_id, {"answer": 1})

        assert exc_info.value.error_code == "recipient_not_found"
        assert exc_info.value.status_code == 410
