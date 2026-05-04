from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Flask
from flask import g


def _load_tenant_role_controller(monkeypatch):
    fake_api_error_module = ModuleType("spiffworkflow_backend.exceptions.api_error")

    class FakeApiError(Exception):
        def __init__(self, error_code: str, message: str, status_code: int):
            super().__init__(message)
            self.error_code = error_code
            self.message = message
            self.status_code = status_code

    fake_api_error_module.ApiError = FakeApiError
    fake_exceptions_package = ModuleType("spiffworkflow_backend.exceptions")
    fake_exceptions_package.api_error = fake_api_error_module

    fake_authz_module = ModuleType("spiffworkflow_backend.services.authorization_service")

    class FakeAuthorizationService:
        @classmethod
        def user_has_permission(cls, *_args, **_kwargs):
            return True

    fake_authz_module.AuthorizationService = FakeAuthorizationService

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions", fake_exceptions_package)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions.api_error", fake_api_error_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.authorization_service", fake_authz_module)

    sys.modules.pop("m8flow_backend.routes.tenant_role_controller", None)
    return import_module("m8flow_backend.routes.tenant_role_controller")


def _mock_user():
    user = MagicMock()
    user.username = "super-admin"
    user.groups = []
    return user


def test_list_tenant_members_returns_service_payload(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "list_tenant_members_with_roles",
        lambda tenant_id, search=None: [{"username": "editor", "roles": ["editor"]}],
    )

    with app.test_request_context("/m8flow/tenants/tenant-it-id/members?search=ed"):
        g.user = _mock_user()
        response = tenant_role_controller.list_tenant_members("tenant-it-id")

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "search": "ed",
        "members": [{"username": "editor", "roles": ["editor"]}],
    }


def test_assign_member_role_returns_updated_member(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "assign_tenant_role",
        lambda tenant_id, username, role_name: {"username": username, "roles": [role_name]},
    )

    with app.test_request_context("/m8flow/tenants/tenant-it-id/members/editor/roles/editor"):
        g.user = _mock_user()
        response = tenant_role_controller.assign_member_role("tenant-it-id", "editor", "editor")

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "username": "editor",
        "role_name": "editor",
        "member": {"username": "editor", "roles": ["editor"]},
    }


def test_remove_member_role_returns_updated_member(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "remove_tenant_role",
        lambda tenant_id, username, role_name: {"username": username, "roles": []},
    )

    with app.test_request_context("/m8flow/tenants/tenant-it-id/members/editor/roles/editor"):
        g.user = _mock_user()
        response = tenant_role_controller.remove_member_role("tenant-it-id", "editor", "editor")

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "username": "editor",
        "role_name": "editor",
        "member": {"username": "editor", "roles": []},
    }
