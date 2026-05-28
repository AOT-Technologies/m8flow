from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType
from types import SimpleNamespace

from flask import Flask


def _load_user_blueprint_patch(monkeypatch):
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

    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_db_module.db = SimpleNamespace(session=SimpleNamespace(add=lambda *_args, **_kwargs: None, commit=lambda: None))

    fake_uga_module = ModuleType("spiffworkflow_backend.models.user_group_assignment")

    class FakeUserGroupAssignmentModel:
        query = SimpleNamespace(filter_by=lambda **_kwargs: SimpleNamespace(first=lambda: None))

        def __init__(self, **kwargs):
            self.id = kwargs.get("id", 1)
            self.user_id = kwargs.get("user_id")
            self.group_id = kwargs.get("group_id")
            self.m8f_tenant_id = kwargs.get("m8f_tenant_id")

    fake_uga_module.UserGroupAssignmentModel = FakeUserGroupAssignmentModel

    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")

    class FakeUserService:
        @classmethod
        def update_human_task_assignments_for_user(cls, *_args, **_kwargs):
            return None

    fake_user_service_module.UserService = FakeUserService

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions", fake_exceptions_package)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions.api_error", fake_api_error_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.user_group_assignment", fake_uga_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.user_service", fake_user_service_module)

    return import_module("m8flow_backend.routes.user_blueprint_patch")


def _install_fake_user_blueprint_module(monkeypatch, user, group) -> None:
    fake_user_blueprint_module = ModuleType("spiffworkflow_backend.routes.user_blueprint")
    fake_user_blueprint_module.get_user_from_request = lambda: user
    fake_user_blueprint_module.get_group_from_request = lambda: group
    fake_user_blueprint_module.assign_user_to_group = lambda: None
    fake_user_blueprint_module.remove_user_from_group = lambda: None

    fake_routes = ModuleType("spiffworkflow_backend.routes")
    fake_routes.user_blueprint = fake_user_blueprint_module

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes", fake_routes)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes.user_blueprint", fake_user_blueprint_module)


def test_assign_user_to_group_syncs_current_tenant_role_membership(monkeypatch) -> None:
    user_blueprint_patch = _load_user_blueprint_patch(monkeypatch)
    app = Flask(__name__)
    user = SimpleNamespace(id=10, username="editor", service="http://localhost:7002/realms/m8flow")
    group = SimpleNamespace(id=20, identifier="tenant-a-id:editor")
    synced: list[tuple[str, str, str, bool]] = []
    updated_assignments: list[tuple[int, set[int], set[int]]] = []

    class FakeQuery:
        def first(self):
            return None

    _install_fake_user_blueprint_module(monkeypatch, user, group)
    monkeypatch.setattr(user_blueprint_patch, "current_tenant_id_or_none", lambda: "tenant-a-id")
    monkeypatch.setattr(
        user_blueprint_patch,
        "_local_assignment_query",
        lambda user_obj, group_obj, tenant_id: FakeQuery(),
    )
    monkeypatch.setattr(
        user_blueprint_patch,
        "_create_local_assignment",
        lambda user_obj, group_obj, tenant_id: SimpleNamespace(id=99),
    )
    monkeypatch.setattr(
        user_blueprint_patch,
        "_sync_shared_realm_role_membership",
        lambda user_obj, role_name, tenant_id, present: synced.append(
            (user_obj.username, role_name, tenant_id, present)
        ),
    )
    monkeypatch.setattr(
        user_blueprint_patch.UserService,
        "update_human_task_assignments_for_user",
        lambda user_obj, new_group_ids, old_group_ids: updated_assignments.append(
            (user_obj.id, set(new_group_ids), set(old_group_ids))
        ),
    )

    with app.test_request_context():
        response = user_blueprint_patch._assign_user_to_group_impl()

    assert response.status_code == 201
    assert response.get_json() == {"id": 99}
    assert synced == [("editor", "editor", "tenant-a-id", True)]
    assert updated_assignments == [(10, {20}, set())]


def test_remove_user_from_group_syncs_current_tenant_role_membership(monkeypatch) -> None:
    user_blueprint_patch = _load_user_blueprint_patch(monkeypatch)
    app = Flask(__name__)
    user = SimpleNamespace(id=10, username="editor", service="http://localhost:7002/realms/m8flow")
    group = SimpleNamespace(id=20, identifier="tenant-a-id:editor")
    synced: list[tuple[str, str, str, bool]] = []
    updated_assignments: list[tuple[int, set[int], set[int]]] = []

    _install_fake_user_blueprint_module(monkeypatch, user, group)
    monkeypatch.setattr(user_blueprint_patch, "current_tenant_id_or_none", lambda: "tenant-a-id")
    monkeypatch.setattr(
        user_blueprint_patch,
        "_delete_local_assignment",
        lambda user_obj, group_obj, tenant_id: SimpleNamespace(id=55),
    )
    monkeypatch.setattr(
        user_blueprint_patch,
        "_sync_shared_realm_role_membership",
        lambda user_obj, role_name, tenant_id, present: synced.append(
            (user_obj.username, role_name, tenant_id, present)
        ),
    )
    monkeypatch.setattr(
        user_blueprint_patch.UserService,
        "update_human_task_assignments_for_user",
        lambda user_obj, new_group_ids, old_group_ids: updated_assignments.append(
            (user_obj.id, set(new_group_ids), set(old_group_ids))
        ),
    )

    with app.test_request_context():
        response = user_blueprint_patch._remove_user_from_group_impl()

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    assert synced == [("editor", "editor", "tenant-a-id", False)]
    assert updated_assignments == [(10, set(), {20})]


def test_assign_user_to_group_rejects_cross_tenant_group(monkeypatch) -> None:
    user_blueprint_patch = _load_user_blueprint_patch(monkeypatch)
    app = Flask(__name__)
    user = SimpleNamespace(id=10, username="editor", service="http://localhost:7002/realms/m8flow")
    group = SimpleNamespace(id=20, identifier="tenant-b-id:editor")

    _install_fake_user_blueprint_module(monkeypatch, user, group)
    monkeypatch.setattr(user_blueprint_patch, "current_tenant_id_or_none", lambda: "tenant-a-id")

    with app.test_request_context():
        try:
            user_blueprint_patch._assign_user_to_group_impl()
        except Exception as exc:
            error = exc
        else:
            error = None

    assert getattr(error, "error_code", None) == "invalid_group"
