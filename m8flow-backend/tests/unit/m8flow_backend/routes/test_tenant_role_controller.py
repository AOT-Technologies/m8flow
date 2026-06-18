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
    tenant_role_controller = import_module("m8flow_backend.routes.tenant_role_controller")
    monkeypatch.setattr(
        tenant_role_controller,
        "require_authorized_user",
        lambda action, forbidden_message, tenant_id=None: SimpleNamespace(username="super-admin"),
    )
    monkeypatch.setattr(
        tenant_role_controller,
        "ensure_request_can_access_tenant",
        lambda tenant_id, forbidden_message: None,
    )
    return tenant_role_controller


def _mock_user():
    user = MagicMock()
    user.username = "super-admin"
    user.groups = []
    return user


def test_list_tenant_members_returns_service_payload(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    service_calls: list[tuple[str, str | None, int, int]] = []
    monkeypatch.setattr(
        tenant_role_controller,
        "list_tenant_members_with_roles",
        lambda tenant_id, search=None, offset=0, max_results=100: service_calls.append(
            (tenant_id, search, offset, max_results)
        )
        or [{"username": "editor", "roles": ["editor"]}],
    )

    with app.test_request_context(
        "/m8flow/tenants/tenant-it-id/members?search=ed&offset=10&limit=10"
    ):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.list_tenant_members("tenant-it-id")

    assert response.status_code == 200
    assert service_calls == [("tenant-it-id", "ed", 10, 11)]
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "search": "ed",
        "offset": 10,
        "limit": 10,
        "has_more": False,
        "members": [{"username": "editor", "roles": ["editor"]}],
    }


def test_list_available_tenant_users_returns_service_payload(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    service_calls: list[tuple[str, str | None, int, int]] = []
    monkeypatch.setattr(
        tenant_role_controller,
        "list_available_tenant_users",
        lambda tenant_id, search=None, offset=0, max_results=100: service_calls.append(
            (tenant_id, search, offset, max_results)
        )
        or [{"username": "editor", "email": "editor@example.com"}],
    )

    with app.test_request_context(
        "/m8flow/tenants/tenant-it-id/available-users?search=ed&offset=10&limit=10"
    ):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.list_available_tenant_users_for_tenant("tenant-it-id")

    assert response.status_code == 200
    assert service_calls == [("tenant-it-id", "ed", 10, 11)]
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "search": "ed",
        "offset": 10,
        "limit": 10,
        "has_more": False,
        "users": [{"username": "editor", "email": "editor@example.com"}],
    }


def test_create_tenant_member_returns_created_member(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "add_tenant_member",
        lambda tenant_id, username, group_names=None: {
            "username": username,
            "email": "reviewer@example.com",
            "roles": ["reviewer"],
        },
    )

    with app.test_request_context(
        "/m8flow/tenants/tenant-it-id/members",
        method="POST",
        json={
            "username": "reviewer",
            "group_names": ["Approvers"],
        },
    ):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.create_tenant_member("tenant-it-id")

    assert response.status_code == 201
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "group_names": ["Approvers"],
        "member": {
            "username": "reviewer",
            "email": "reviewer@example.com",
            "roles": ["reviewer"],
        },
    }


def test_list_tenant_groups_returns_service_payload(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    service_calls: list[tuple[str, str | None, int, int]] = []
    monkeypatch.setattr(
        tenant_role_controller,
        "list_tenant_groups_with_members",
        lambda tenant_id, search=None, offset=0, max_results=100: service_calls.append(
            (tenant_id, search, offset, max_results)
        )
        or [
            {
                "name": "Administrators",
                "mapped_roles": ["tenant-admin"],
                "members": [{"username": "admin"}],
            }
        ],
    )

    with app.test_request_context(
        "/m8flow/tenants/tenant-it-id/groups?search=admin&offset=10&limit=10"
    ):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.list_tenant_groups("tenant-it-id")

    assert response.status_code == 200
    assert service_calls == [("tenant-it-id", "admin", 10, 11)]
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "search": "admin",
        "offset": 10,
        "limit": 10,
        "has_more": False,
        "groups": [
            {
                "name": "Administrators",
                "mapped_roles": ["tenant-admin"],
                "members": [{"username": "admin"}],
            }
        ],
    }


def test_update_group_returns_updated_group(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "rename_tenant_group",
        lambda tenant_id, group_name, new_group_name: {
            "id": "group-approvers",
            "name": new_group_name,
            "mapped_roles": ["reviewer"],
            "members": [{"username": "reviewer"}],
        },
    )

    with app.test_request_context(
        "/m8flow/tenants/tenant-it-id/groups/Approvers",
        method="PUT",
        json={"name": "QA Reviewers"},
    ):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.update_group("tenant-it-id", "Approvers")

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "previous_group_name": "Approvers",
        "group": {
            "id": "group-approvers",
            "name": "QA Reviewers",
            "mapped_roles": ["reviewer"],
            "members": [{"username": "reviewer"}],
        },
    }


def test_assign_group_member_returns_updated_member(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "add_tenant_group_member",
        lambda tenant_id, username, group_name: {
            "username": username,
            "roles": ["reviewer"],
        },
    )

    with app.test_request_context("/m8flow/tenants/tenant-it-id/groups/Approvers/members/reviewer"):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.assign_group_member(
            "tenant-it-id",
            "Approvers",
            "reviewer",
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "group_name": "Approvers",
        "username": "reviewer",
        "member": {"username": "reviewer", "roles": ["reviewer"]},
    }


def test_remove_group_member_returns_updated_member(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "remove_tenant_group_member",
        lambda tenant_id, username, group_name: {
            "username": username,
            "roles": [],
        },
    )

    with app.test_request_context("/m8flow/tenants/tenant-it-id/groups/Approvers/members/reviewer"):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.remove_group_member(
            "tenant-it-id",
            "Approvers",
            "reviewer",
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "group_name": "Approvers",
        "username": "reviewer",
        "member": {"username": "reviewer", "roles": []},
    }


def test_assign_group_role_returns_updated_group(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "assign_tenant_group_role",
        lambda tenant_id, group_name, role_name: {
            "name": group_name,
            "mapped_roles": [role_name],
            "members": [],
        },
    )

    with app.test_request_context("/m8flow/tenants/tenant-it-id/groups/Approvers/roles/reviewer"):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.assign_group_role(
            "tenant-it-id",
            "Approvers",
            "reviewer",
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "group_name": "Approvers",
        "role_name": "reviewer",
        "group": {"name": "Approvers", "mapped_roles": ["reviewer"], "members": []},
    }


def test_remove_group_role_returns_updated_group(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "remove_tenant_group_role",
        lambda tenant_id, group_name, role_name: {
            "name": group_name,
            "mapped_roles": [],
            "members": [],
        },
    )

    with app.test_request_context("/m8flow/tenants/tenant-it-id/groups/Approvers/roles/reviewer"):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.remove_group_role(
            "tenant-it-id",
            "Approvers",
            "reviewer",
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "group_name": "Approvers",
        "role_name": "reviewer",
        "group": {"name": "Approvers", "mapped_roles": [], "members": []},
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
        g._m8flow_super_admin_request = True
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
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.remove_member_role("tenant-it-id", "editor", "editor")

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "username": "editor",
        "role_name": "editor",
        "member": {"username": "editor", "roles": []},
    }


def test_create_group_returns_created_group(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "create_tenant_group",
        lambda tenant_id, group_name: {
            "id": "group-manager",
            "name": group_name,
            "mapped_roles": [],
            "member_count": 0,
            "members": [],
            "path": f"/{group_name}",
        },
    )

    with app.test_request_context(
        "/m8flow/tenants/tenant-it-id/groups",
        method="POST",
        json={"name": "Manager"},
    ):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.create_group("tenant-it-id")

    assert response.status_code == 201
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "group": {
            "id": "group-manager",
            "name": "Manager",
            "mapped_roles": [],
            "member_count": 0,
            "members": [],
            "path": "/Manager",
        },
    }


def test_remove_group_returns_deleted_group_name(monkeypatch):
    tenant_role_controller = _load_tenant_role_controller(monkeypatch)
    app = Flask(__name__)
    monkeypatch.setattr(
        tenant_role_controller,
        "delete_tenant_group",
        lambda tenant_id, group_name: group_name,
    )

    with app.test_request_context("/m8flow/tenants/tenant-it-id/groups/Approvers"):
        g.user = _mock_user()
        g._m8flow_super_admin_request = True
        response = tenant_role_controller.remove_group("tenant-it-id", "Approvers")

    assert response.status_code == 200
    assert response.get_json() == {
        "tenant_id": "tenant-it-id",
        "group_name": "Approvers",
    }
