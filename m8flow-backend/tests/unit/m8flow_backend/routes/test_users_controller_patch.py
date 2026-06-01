from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType
from types import SimpleNamespace

from flask import Flask, g


def test_user_group_list_filters_to_current_tenant_hides_default_group_and_keeps_global_super_admin(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"

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
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions", fake_exceptions_package)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions.api_error", fake_api_error_module)

    fake_users_controller = ModuleType("spiffworkflow_backend.routes.users_controller")
    fake_users_controller.user_exists_by_username = lambda body: body
    fake_users_controller.user_search = lambda prefix: prefix
    fake_users_controller.user_group_list_for_current_user = lambda: None

    fake_routes = ModuleType("spiffworkflow_backend.routes")
    fake_routes.users_controller = fake_users_controller

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes", fake_routes)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes.users_controller", fake_users_controller)
    users_controller_patch = import_module("m8flow_backend.routes.users_controller_patch")
    monkeypatch.setattr(users_controller_patch, "_PATCHED", False)
    monkeypatch.setattr(
        users_controller_patch,
        "qualified_config_group_identifier",
        lambda config_key: "tenant-a:everybody",
    )
    monkeypatch.setattr(users_controller_patch, "current_tenant_id_or_none", lambda: "tenant-a")
    monkeypatch.setattr(
        users_controller_patch,
        "is_group_for_tenant",
        lambda group_identifier, tenant_id: group_identifier.startswith(f"{tenant_id}:"),
    )

    users_controller_patch.apply()

    with app.app_context():
        with app.test_request_context():
            g.user = SimpleNamespace(
                groups=[
                    SimpleNamespace(identifier="tenant-a:reviewer"),
                    SimpleNamespace(identifier="tenant-a:everybody"),
                    SimpleNamespace(identifier="tenant-a:admin"),
                    SimpleNamespace(identifier="tenant-b:viewer"),
                    SimpleNamespace(identifier="super-admin"),
                ]
            )
            response = fake_users_controller.user_group_list_for_current_user()

    assert response.status_code == 200
    assert response.get_json() == ["super-admin", "tenant-a:admin", "tenant-a:reviewer"]
