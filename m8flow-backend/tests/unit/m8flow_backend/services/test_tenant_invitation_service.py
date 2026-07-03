"""Unit tests for the tenant invitation service (token hashing, expiry, single-use, roles)."""
# ruff: noqa: E402
import sys
import time
from pathlib import Path

import pytest
from flask import Flask

# Ensure m8flow_backend and spiffworkflow_backend are importable
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"
for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from m8flow_backend.models.tenant_invitation import (
    M8flowTenantInvitationModel,
    TenantInvitationStatus,
)
from m8flow_backend.services import tenant_invitation_service as svc
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import add_listeners, db

TENANT_ID = "tenant-1"


@pytest.fixture
def app():
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)
    with app.app_context():
        db.create_all()
        add_listeners()
        tenant = M8flowTenantModel(
            id=TENANT_ID,
            name="Acme Corp",
            slug="acme-corp",
            status=TenantStatus.ACTIVE,
            created_by="admin",
            modified_by="admin",
        )
        db.session.add(tenant)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def stub_external(monkeypatch):
    """Stub Keycloak + email so the service can be tested without external services."""
    monkeypatch.setattr(svc, "get_realm_user_by_username", lambda *a, **k: None)
    monkeypatch.setattr(svc, "send_email", lambda *a, **k: False)  # dev mode (not sent)
    monkeypatch.setattr(svc, "smtp_is_configured", lambda: False)
    monkeypatch.setattr(svc, "shared_realm_name", lambda: "m8flow")
    created = {}
    monkeypatch.setattr(
        svc, "create_user_in_realm", lambda realm, username, password, email=None: created.setdefault("user", username) or "user-id"
    )
    members = []
    monkeypatch.setattr(
        svc, "add_tenant_member", lambda tenant_id, username, group_names: members.append((tenant_id, username, tuple(group_names)))
    )
    return {"created": created, "members": members}


class TestCreateInvitation:
    def test_create_returns_pending_with_dev_link(self, app):
        with app.app_context():
            result = svc.create_invitation(TENANT_ID, "user@example.com", ["editor"], 7, "admin")
            assert result["status"] == "PENDING"
            assert result["email"] == "user@example.com"
            assert result["roles"] == ["editor"]
            # Dev mode (no SMTP) surfaces the link.
            assert "invitation_link" in result and "token=" in result["invitation_link"]

    def test_rejects_invalid_email(self, app):
        with app.app_context():
            with pytest.raises(ApiError):
                svc.create_invitation(TENANT_ID, "not-an-email", ["editor"], 7, "admin")

    def test_rejects_empty_roles(self, app):
        with app.app_context():
            with pytest.raises(ApiError):
                svc.create_invitation(TENANT_ID, "user@example.com", [], 7, "admin")

    def test_rejects_invalid_roles(self, app):
        with app.app_context():
            with pytest.raises(ApiError):
                svc.create_invitation(TENANT_ID, "user@example.com", ["not-a-role"], 7, "admin")

    def test_rejects_duplicate_pending_invitation(self, app):
        with app.app_context():
            svc.create_invitation(TENANT_ID, "dup@example.com", ["editor"], 7, "admin")
            with pytest.raises(ApiError) as exc:
                svc.create_invitation(TENANT_ID, "dup@example.com", ["viewer"], 7, "admin")
            assert exc.value.status_code == 409

    def test_clamps_validity_days(self, app):
        with app.app_context():
            result = svc.create_invitation(TENANT_ID, "v@example.com", ["editor"], 999, "admin")
            # Clamped to MAX_VALIDITY_DAYS.
            assert result["expires_at_in_seconds"] <= int(time.time()) + svc.MAX_VALIDITY_DAYS * 86400 + 5


def _raw_token_for(app):
    """Create an invitation and return its raw token by re-deriving via monkeypatch-free flow."""
    # create_invitation hashes the token; to test validate/accept we read the link's token.
    result = svc.create_invitation(TENANT_ID, "flow@example.com", ["editor", "viewer"], 7, "admin")
    link = result["invitation_link"]
    return link.split("token=", 1)[1]


class TestValidateAndAccept:
    def test_validate_returns_metadata(self, app):
        with app.app_context():
            token = _raw_token_for(app)
            meta = svc.validate_token(token)
            assert meta["email"] == "flow@example.com"
            assert meta["tenant_name"] == "Acme Corp"
            assert set(meta["roles"]) == {"editor", "viewer"}

    def test_invalid_token_rejected(self, app):
        with app.app_context():
            with pytest.raises(ApiError) as exc:
                svc.validate_token("totally-wrong-token")
            assert exc.value.status_code == 404

    def test_accept_activates_and_is_single_use(self, app, stub_external):
        with app.app_context():
            token = _raw_token_for(app)
            result = svc.accept_invitation(token, "password123")
            assert result["email"] == "flow@example.com"
            assert stub_external["created"]["user"] == "flow@example.com"
            assert stub_external["members"][0][1] == "flow@example.com"
            # Token can no longer be validated or accepted (single-use).
            with pytest.raises(ApiError):
                svc.validate_token(token)
            with pytest.raises(ApiError):
                svc.accept_invitation(token, "password123")

    def test_accept_rejects_weak_password(self, app):
        with app.app_context():
            token = _raw_token_for(app)
            with pytest.raises(ApiError) as exc:
                svc.accept_invitation(token, "short")
            assert exc.value.status_code == 400

    def test_expired_token_rejected(self, app):
        with app.app_context():
            token = _raw_token_for(app)
            invitation = M8flowTenantInvitationModel.query.filter_by(email="flow@example.com").first()
            invitation.expires_at_in_seconds = int(time.time()) - 10
            db.session.commit()
            with pytest.raises(ApiError) as exc:
                svc.validate_token(token)
            assert exc.value.status_code == 410
            # Lazily flipped to EXPIRED.
            refreshed = M8flowTenantInvitationModel.query.filter_by(email="flow@example.com").first()
            assert refreshed.status == TenantInvitationStatus.EXPIRED

    def test_revoked_token_rejected(self, app):
        with app.app_context():
            token = _raw_token_for(app)
            invitation = M8flowTenantInvitationModel.query.filter_by(email="flow@example.com").first()
            svc.revoke_invitation(TENANT_ID, invitation.id, "admin")
            with pytest.raises(ApiError):
                svc.validate_token(token)


class TestTokenHashing:
    def test_raw_token_not_stored(self, app):
        with app.app_context():
            token = _raw_token_for(app)
            invitation = M8flowTenantInvitationModel.query.filter_by(email="flow@example.com").first()
            assert invitation.token_hash != token
            assert invitation.token_hash == svc._hash_token(token)


class TestListInvitations:
    def test_returns_paginated_results(self, app):
        with app.app_context():
            svc.create_invitation(TENANT_ID, "a@example.com", ["editor"], 7, "admin")
            svc.create_invitation(TENANT_ID, "b@example.com", ["viewer"], 7, "admin")
            page = svc.list_invitations(TENANT_ID, offset=0, limit=10)
            assert page["total"] == 2
            assert page["offset"] == 0
            assert page["limit"] == 10
            assert {row["email"] for row in page["results"]} == {"a@example.com", "b@example.com"}

    def test_status_filter(self, app):
        with app.app_context():
            svc.create_invitation(TENANT_ID, "pending@example.com", ["editor"], 7, "admin")
            invitation = M8flowTenantInvitationModel.query.filter_by(email="pending@example.com").first()
            svc.revoke_invitation(TENANT_ID, invitation.id, "admin")
            svc.create_invitation(TENANT_ID, "still-pending@example.com", ["editor"], 7, "admin")

            revoked = svc.list_invitations(TENANT_ID, status_filter="revoked")
            assert [row["email"] for row in revoked["results"]] == ["pending@example.com"]

            pending = svc.list_invitations(TENANT_ID, status_filter="PENDING")
            assert [row["email"] for row in pending["results"]] == ["still-pending@example.com"]

    def test_lazily_expires_pending_during_listing(self, app):
        with app.app_context():
            svc.create_invitation(TENANT_ID, "old@example.com", ["editor"], 7, "admin")
            invitation = M8flowTenantInvitationModel.query.filter_by(email="old@example.com").first()
            invitation.expires_at_in_seconds = int(time.time()) - 10
            db.session.commit()

            page = svc.list_invitations(TENANT_ID)
            assert page["results"][0]["status"] == "EXPIRED"
            refreshed = M8flowTenantInvitationModel.query.filter_by(email="old@example.com").first()
            assert refreshed.status == TenantInvitationStatus.EXPIRED


class TestResendInvitation:
    def test_rotates_token_and_keeps_pending(self, app):
        with app.app_context():
            result = svc.create_invitation(TENANT_ID, "resend@example.com", ["editor"], 7, "admin")
            old_token = result["invitation_link"].split("token=", 1)[1]
            invitation = M8flowTenantInvitationModel.query.filter_by(email="resend@example.com").first()

            resent = svc.resend_invitation(TENANT_ID, invitation.id, "admin")
            new_token = resent["invitation_link"].split("token=", 1)[1]

            assert new_token != old_token
            assert resent["status"] == "PENDING"
            # Old token no longer validates; new one does.
            with pytest.raises(ApiError):
                svc.validate_token(old_token)
            assert svc.validate_token(new_token)["email"] == "resend@example.com"

    def test_re_pends_an_expired_invitation(self, app):
        with app.app_context():
            svc.create_invitation(TENANT_ID, "exp@example.com", ["editor"], 7, "admin")
            invitation = M8flowTenantInvitationModel.query.filter_by(email="exp@example.com").first()
            invitation.expires_at_in_seconds = int(time.time()) - 10
            db.session.commit()

            resent = svc.resend_invitation(TENANT_ID, invitation.id, "admin")
            assert resent["status"] == "PENDING"
            assert resent["expires_at_in_seconds"] > int(time.time())

    def test_rejects_resending_accepted(self, app, stub_external):
        with app.app_context():
            token = _raw_token_for(app)
            svc.accept_invitation(token, "password123")
            invitation = M8flowTenantInvitationModel.query.filter_by(email="flow@example.com").first()
            with pytest.raises(ApiError) as exc:
                svc.resend_invitation(TENANT_ID, invitation.id, "admin")
            assert exc.value.status_code == 409


class TestRevokeInvitation:
    def test_rejects_revoking_accepted(self, app, stub_external):
        with app.app_context():
            token = _raw_token_for(app)
            svc.accept_invitation(token, "password123")
            invitation = M8flowTenantInvitationModel.query.filter_by(email="flow@example.com").first()
            with pytest.raises(ApiError) as exc:
                svc.revoke_invitation(TENANT_ID, invitation.id, "admin")
            assert exc.value.status_code == 409


class TestValidityDays:
    def test_clamps_below_one_to_minimum(self):
        assert svc._validity_days(0) == 1
        assert svc._validity_days(-5) == 1

    def test_clamps_above_maximum(self):
        assert svc._validity_days(999) == svc.MAX_VALIDITY_DAYS

    def test_non_int_falls_back_to_default(self):
        assert svc._validity_days(None) == svc.DEFAULT_VALIDITY_DAYS
        assert svc._validity_days("abc") == svc.DEFAULT_VALIDITY_DAYS
