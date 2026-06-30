"""Unit tests for the tenant invitation controller routes.

The controller wraps the invitation service with super-admin authorization for the
management endpoints and exposes two public endpoints (validate + accept). Service
functions and authorization helpers are stubbed; we assert request parsing, the
authorization gate, and the response shape.
"""
# ruff: noqa: E402
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Flask, g

# Ensure m8flow_backend and spiffworkflow_backend are importable
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"
for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.routes import tenant_invitation_controller as controller

TENANT_ID = "tenant-1"


@pytest.fixture
def app():
    return Flask(__name__)  # NOSONAR - unit test, no HTTP/CSRF involved


@pytest.fixture
def mock_user():
    user = Mock()
    user.username = "super-admin"
    return user


@pytest.fixture(autouse=True)
def stub_auth(monkeypatch):
    """Authorize as super-admin by default; individual tests can flip the gate."""
    monkeypatch.setattr(
        controller,
        "require_authorized_user",
        lambda action, tenant_id=None, forbidden_message=None: Mock(username="super-admin"),
    )
    monkeypatch.setattr(controller, "ensure_request_can_access_tenant", lambda *a, **k: None)
    monkeypatch.setattr(controller, "is_super_admin_request", lambda: True)


class TestCreateTenantInvitation:
    def test_passes_payload_to_service(self, app, mock_user, monkeypatch):
        calls = {}
        monkeypatch.setattr(
            controller,
            "create_invitation",
            lambda tenant_id, email, roles, validity_days, created_by: calls.update(
                tenant_id=tenant_id, email=email, roles=roles,
                validity_days=validity_days, created_by=created_by,
            )
            or {"id": "inv-1", "status": "PENDING"},
        )
        with app.test_request_context(
            f"/m8flow/tenants/{TENANT_ID}/invitations",
            method="POST",
            json={"email": "user@example.com", "roles": ["editor"], "validity_days": 7},
        ):
            g.user = mock_user
            response = controller.create_tenant_invitation(TENANT_ID)

        assert response.status_code == 201
        assert response.get_json() == {
            "tenant_id": TENANT_ID,
            "invitation": {"id": "inv-1", "status": "PENDING"},
        }
        assert calls == {
            "tenant_id": TENANT_ID,
            "email": "user@example.com",
            "roles": ["editor"],
            "validity_days": 7,
            "created_by": "super-admin",
        }

    def test_forbidden_when_not_super_admin(self, app, mock_user, monkeypatch):
        monkeypatch.setattr(controller, "is_super_admin_request", lambda: False)
        called = {"hit": False}
        monkeypatch.setattr(
            controller, "create_invitation", lambda *a, **k: called.update(hit=True)
        )
        with app.test_request_context(
            f"/m8flow/tenants/{TENANT_ID}/invitations",
            method="POST",
            json={"email": "user@example.com", "roles": ["editor"]},
        ):
            g.user = mock_user
            response = controller.create_tenant_invitation(TENANT_ID)

        assert response.status_code == 403
        assert called["hit"] is False


class TestListTenantInvitations:
    def test_parses_and_clamps_query_args(self, app, mock_user, monkeypatch):
        calls = {}
        monkeypatch.setattr(
            controller,
            "list_invitations",
            lambda tenant_id, status_filter, offset, limit: calls.update(
                tenant_id=tenant_id, status_filter=status_filter, offset=offset, limit=limit
            )
            or {"results": [], "total": 0, "offset": offset, "limit": limit},
        )
        with app.test_request_context(
            f"/m8flow/tenants/{TENANT_ID}/invitations?status=PENDING&offset=5&limit=999"
        ):
            g.user = mock_user
            response = controller.list_tenant_invitations(TENANT_ID)

        assert response.status_code == 200
        body = response.get_json()
        assert body["tenant_id"] == TENANT_ID
        # limit clamped to MAX_INVITATION_PAGE_SIZE.
        assert calls["offset"] == 5
        assert calls["limit"] == controller.MAX_INVITATION_PAGE_SIZE
        assert calls["status_filter"] == "PENDING"

    def test_defaults_when_query_args_absent(self, app, mock_user, monkeypatch):
        calls = {}
        monkeypatch.setattr(
            controller,
            "list_invitations",
            lambda tenant_id, status_filter, offset, limit: calls.update(
                offset=offset, limit=limit, status_filter=status_filter
            )
            or {"results": [], "total": 0, "offset": offset, "limit": limit},
        )
        with app.test_request_context(f"/m8flow/tenants/{TENANT_ID}/invitations"):
            g.user = mock_user
            controller.list_tenant_invitations(TENANT_ID)

        assert calls["offset"] == 0
        assert calls["limit"] == controller.DEFAULT_INVITATION_PAGE_SIZE
        assert calls["status_filter"] is None


class TestResendAndRevoke:
    def test_resend_calls_service(self, app, mock_user, monkeypatch):
        calls = {}
        monkeypatch.setattr(
            controller,
            "resend_invitation",
            lambda tenant_id, invitation_id, modified_by: calls.update(
                tenant_id=tenant_id, invitation_id=invitation_id, modified_by=modified_by
            )
            or {"id": invitation_id, "status": "PENDING"},
        )
        with app.test_request_context(
            f"/m8flow/tenants/{TENANT_ID}/invitations/inv-1/resend", method="POST"
        ):
            g.user = mock_user
            response = controller.resend_tenant_invitation(TENANT_ID, "inv-1")

        assert response.status_code == 200
        assert calls == {"tenant_id": TENANT_ID, "invitation_id": "inv-1", "modified_by": "super-admin"}

    def test_revoke_calls_service(self, app, mock_user, monkeypatch):
        calls = {}
        monkeypatch.setattr(
            controller,
            "revoke_invitation",
            lambda tenant_id, invitation_id, modified_by: calls.update(
                tenant_id=tenant_id, invitation_id=invitation_id, modified_by=modified_by
            )
            or {"id": invitation_id, "status": "REVOKED"},
        )
        with app.test_request_context(
            f"/m8flow/tenants/{TENANT_ID}/invitations/inv-1", method="DELETE"
        ):
            g.user = mock_user
            response = controller.revoke_tenant_invitation(TENANT_ID, "inv-1")

        assert response.status_code == 200
        assert response.get_json()["invitation"]["status"] == "REVOKED"
        assert calls["invitation_id"] == "inv-1"

    def test_revoke_forbidden_when_not_super_admin(self, app, mock_user, monkeypatch):
        monkeypatch.setattr(controller, "is_super_admin_request", lambda: False)
        called = {"hit": False}
        monkeypatch.setattr(controller, "revoke_invitation", lambda *a, **k: called.update(hit=True))
        with app.test_request_context(
            f"/m8flow/tenants/{TENANT_ID}/invitations/inv-1", method="DELETE"
        ):
            g.user = mock_user
            response = controller.revoke_tenant_invitation(TENANT_ID, "inv-1")

        assert response.status_code == 403
        assert called["hit"] is False


class TestPublicEndpoints:
    def test_validate_reads_token_query_arg(self, app, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            controller,
            "validate_token",
            lambda token: seen.update(token=token) or {"email": "user@example.com", "roles": ["editor"]},
        )
        with app.test_request_context("/m8flow/invitations/validate?token=raw-token"):
            response = controller.validate_invitation()

        assert response.status_code == 200
        assert seen["token"] == "raw-token"
        assert response.get_json()["email"] == "user@example.com"

    def test_accept_passes_token_and_password(self, app, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            controller,
            "accept_invitation",
            lambda token, password: seen.update(token=token, password=password)
            or {"email": "user@example.com", "smtp_configured": False},
        )
        with app.test_request_context(
            "/m8flow/invitations/accept",
            method="POST",
            json={"token": "raw-token", "password": "password123"},
        ):
            response = controller.accept_tenant_invitation()

        assert response.status_code == 200
        assert seen == {"token": "raw-token", "password": "password123"}
