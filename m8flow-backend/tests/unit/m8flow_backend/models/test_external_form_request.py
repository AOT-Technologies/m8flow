"""Unit tests for ExternalFormRequestModel (M8F-338).

Tests cover:
- Model creation with required fields and defaults
- reference_id uniqueness at database level
- Status lifecycle values and is_actionable()
- Timestamp auto-population via AuditDateTimeMixin
- to_public_dict shape (no recipient PII)
"""
import sys
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

# Setup path for imports
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.external_form_request import (  # noqa: E402
    ACTIONABLE_STATUSES,
    ExternalFormRequestModel,
    ExternalFormRequestStatus,
)
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.models.db import add_listeners  # noqa: E402
from spiffworkflow_backend.models.user import UserModel  # noqa: E402


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
def recipient(app):
    user = UserModel(username="alice", service="test", service_id="alice", email="alice@example.com")
    db.session.add(user)
    db.session.commit()
    return user


def _make_request_row(tenant, recipient, **overrides):
    values = {
        "m8f_tenant_id": tenant.id,
        "reference_id": "ref-abc-123",
        "process_instance_id": 42,
        "task_guid": "11111111-2222-3333-4444-555555555555",
        "recipient_user_id": recipient.id,
        "email": recipient.email,
        "external_form_url": "https://forms.example.com/leave-request",
    }
    values.update(overrides)
    return ExternalFormRequestModel(**values)


class TestExternalFormRequestModel:
    def test_create_with_required_fields_and_defaults(self, app, tenant, recipient):
        row = _make_request_row(tenant, recipient)
        db.session.add(row)
        db.session.commit()

        saved = ExternalFormRequestModel.query.filter_by(reference_id="ref-abc-123").first()
        assert saved is not None
        assert saved.status == ExternalFormRequestStatus.pending.value
        assert saved.attempts == 0
        assert saved.form_submission_data is None
        assert saved.external_form_url == "https://forms.example.com/leave-request"

    def test_reference_id_unique_constraint(self, app, tenant, recipient):
        db.session.add(_make_request_row(tenant, recipient))
        db.session.commit()

        db.session.add(_make_request_row(tenant, recipient))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_timestamps_auto_populated(self, app, tenant, recipient):
        row = _make_request_row(tenant, recipient)
        db.session.add(row)
        db.session.commit()

        assert isinstance(row.created_at_in_seconds, int)
        assert row.created_at_in_seconds > 0
        assert isinstance(row.updated_at_in_seconds, int)
        assert row.updated_at_in_seconds > 0

    def test_is_actionable_per_status(self, app, tenant, recipient):
        row = _make_request_row(tenant, recipient)
        for status in ExternalFormRequestStatus:
            row.status = status.value
            assert row.is_actionable() == (status.value in ACTIONABLE_STATUSES)

        assert ExternalFormRequestStatus.pending.value in ACTIONABLE_STATUSES
        assert ExternalFormRequestStatus.notified.value in ACTIONABLE_STATUSES
        assert ExternalFormRequestStatus.failed.value in ACTIONABLE_STATUSES
        assert ExternalFormRequestStatus.completed.value not in ACTIONABLE_STATUSES
        assert ExternalFormRequestStatus.superseded.value not in ACTIONABLE_STATUSES

    def test_form_submission_data_json_roundtrip(self, app, tenant, recipient):
        row = _make_request_row(tenant, recipient)
        row.form_submission_data = {"answer": 42, "nested": {"ok": True}}
        db.session.add(row)
        db.session.commit()

        saved = ExternalFormRequestModel.query.filter_by(reference_id="ref-abc-123").first()
        assert saved.form_submission_data == {"answer": 42, "nested": {"ok": True}}

    def test_to_public_dict_has_no_recipient_pii(self, app, tenant, recipient):
        row = _make_request_row(tenant, recipient, user_details={"name": "Alice"})
        db.session.add(row)
        db.session.commit()

        public = row.to_public_dict()
        assert public == {
            "reference_id": "ref-abc-123",
            "status": ExternalFormRequestStatus.pending.value,
            "external_form_url": "https://forms.example.com/leave-request",
            "process_instance_id": 42,
        }
        assert "email" not in public
        assert "user_details" not in public

    def test_multiple_recipients_same_task(self, app, tenant, recipient):
        other = UserModel(username="bob", service="test", service_id="bob", email="bob@example.com")
        db.session.add(other)
        db.session.commit()

        db.session.add(_make_request_row(tenant, recipient, reference_id="ref-alice"))
        db.session.add(_make_request_row(tenant, other, reference_id="ref-bob", recipient_user_id=other.id))
        db.session.commit()

        rows = ExternalFormRequestModel.query.filter_by(
            process_instance_id=42, task_guid="11111111-2222-3333-4444-555555555555"
        ).all()
        assert len(rows) == 2
        assert {r.reference_id for r in rows} == {"ref-alice", "ref-bob"}
