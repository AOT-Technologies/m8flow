from __future__ import annotations

import importlib
import sys
from types import ModuleType
from types import SimpleNamespace

from flask import Flask, g


class FakeSecret:
    def __init__(self, key: str, user_id: int, value: str = "enc:vault-value") -> None:
        self.key = key
        self.user_id = user_id
        self.value = value

    def to_dict(self) -> dict[str, object]:
        return {
            "id": "secret-1",
            "key": self.key,
            "user_id": self.user_id,
            "created_at_in_seconds": 1,
            "updated_at_in_seconds": 2,
        }


class FakeSecretBackend:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def get_secret(self, key: str) -> FakeSecret:
        self.calls.append(("get_secret", key))
        return FakeSecret(key=key, user_id=7)

    def add_secret(self, key: str, value: str, user_id: int) -> FakeSecret:
        self.calls.append(("add_secret", key, value, user_id))
        return FakeSecret(key=key, user_id=user_id)

    def update_secret(
        self,
        key: str,
        value: str,
        user_id: int | None = None,
        create_if_not_exists: bool | None = False,
        new_key: str | None = None,
    ) -> None:
        self.calls.append(("update_secret", key, value, user_id, create_if_not_exists, new_key))

    def delete_secret(self, key: str, user_id: int) -> None:
        self.calls.append(("delete_secret", key, user_id))

    def serialize_secret_list_result(
        self,
        page: int = 1,
        per_page: int = 100,
        tenant_id: str | None = None,
    ) -> dict[str, object]:
        self.calls.append(("serialize_secret_list_result", page, per_page, tenant_id))
        effective_tenant_id = tenant_id or "tenant-from-context"
        return {
            "results": [
                {
                    "key": "API_TOKEN",
                    "tenantId": effective_tenant_id,
                    "tenantName": f"Tenant {effective_tenant_id}",
                    "username": "vault-user",
                }
            ],
            "pagination": {"count": 1, "total": 1, "pages": 1},
        }


def _load_patch(monkeypatch, backend: FakeSecretBackend, state: dict[str, bool]):
    fake_secrets_controller = ModuleType("spiffworkflow_backend.routes.secrets_controller")
    fake_secrets_controller.secret_show = lambda key: None
    fake_secrets_controller.secret_show_value = lambda key: None
    fake_secrets_controller.secret_create = lambda body: None
    fake_secrets_controller.secret_update = lambda key, body: None
    fake_secrets_controller.secret_delete = lambda key: None
    fake_secrets_controller.secret_list = lambda page=1, per_page=100: None

    fake_routes = ModuleType("spiffworkflow_backend.routes")
    fake_routes.__path__ = []
    fake_routes.secrets_controller = fake_secrets_controller

    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")

    class FakeUserService:
        @staticmethod
        def current_user():
            return SimpleNamespace(id=99)

    fake_user_service_module.UserService = FakeUserService

    fake_services = ModuleType("spiffworkflow_backend.services")
    fake_services.__path__ = []

    fake_secret_backend_module = ModuleType("m8flow_backend.services.secret_backend")
    fake_secret_backend_module.get_secret_backend = lambda: backend

    fake_tenancy_module = ModuleType("m8flow_backend.tenancy")
    fake_tenancy_module.is_super_admin_request = lambda: state["is_super_admin"]

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes", fake_routes)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes.secrets_controller", fake_secrets_controller)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services", fake_services)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.user_service", fake_user_service_module)
    monkeypatch.setitem(sys.modules, "m8flow_backend.services.secret_backend", fake_secret_backend_module)
    monkeypatch.setitem(sys.modules, "m8flow_backend.tenancy", fake_tenancy_module)

    sys.modules.pop("m8flow_backend.routes.secrets_controller_patch", None)
    patch_module = importlib.import_module("m8flow_backend.routes.secrets_controller_patch")
    monkeypatch.setattr(patch_module, "_PATCHED", False)
    patch_module.apply()
    return fake_secrets_controller


def test_secret_crud_routes_delegate_to_common_backend(monkeypatch) -> None:
    backend = FakeSecretBackend()
    state = {"is_super_admin": False}
    secrets_controller = _load_patch(monkeypatch, backend, state)
    app = Flask(__name__)

    with app.app_context():
        with app.test_request_context("/"):
            g.user = SimpleNamespace(id=7)

            show_response = secrets_controller.secret_show("API_TOKEN")
            show_value_response = secrets_controller.secret_show_value("API_TOKEN")
            create_response = secrets_controller.secret_create({"key": "API_TOKEN", "value": "vault-value"})
            update_response = secrets_controller.secret_update(
                "API_TOKEN",
                {"key": "API_TOKEN_NEW", "value": "rotated-value"},
            )
            delete_response = secrets_controller.secret_delete("API_TOKEN")

    assert show_response.status_code == 200
    assert show_response.get_json()["key"] == "API_TOKEN"

    assert show_value_response.status_code == 404
    assert show_value_response.get_json() == {
        "error_code": "secret_value_retrieval_disabled",
        "message": "Retrieving secret values through this endpoint is disabled in M8Flow.",
    }

    assert create_response.status_code == 201
    assert create_response.get_json()["user_id"] == 7

    assert update_response.status_code == 200
    assert update_response.get_json() == {"ok": True}

    assert delete_response.status_code == 200
    assert delete_response.get_json() == {"ok": True}

    assert backend.calls == [
        ("get_secret", "API_TOKEN"),
        ("add_secret", "API_TOKEN", "vault-value", 7),
        ("update_secret", "API_TOKEN", "rotated-value", 7, False, "API_TOKEN_NEW"),
        ("delete_secret", "API_TOKEN", 99),
    ]


def test_secret_list_delegates_to_common_backend_with_super_admin_filter(monkeypatch) -> None:
    backend = FakeSecretBackend()
    state = {"is_super_admin": True}
    secrets_controller = _load_patch(monkeypatch, backend, state)
    app = Flask(__name__)

    with app.app_context():
        with app.test_request_context("/?tenantId=tenant-b"):
            response = secrets_controller.secret_list(page=2, per_page=25)

        state["is_super_admin"] = False
        with app.test_request_context("/?tenantId=tenant-c"):
            default_response = secrets_controller.secret_list(page=3, per_page=10)

    assert response.status_code == 200
    assert response.get_json()["results"][0] == {
        "key": "API_TOKEN",
        "tenantId": "tenant-b",
        "tenantName": "Tenant tenant-b",
        "username": "vault-user",
    }

    assert default_response.status_code == 200
    assert default_response.get_json()["results"][0] == {
        "key": "API_TOKEN",
        "tenantId": "tenant-from-context",
        "tenantName": "Tenant tenant-from-context",
        "username": "vault-user",
    }

    assert backend.calls == [
        ("serialize_secret_list_result", 2, 25, "tenant-b"),
        ("serialize_secret_list_result", 3, 10, None),
    ]


def test_secret_list_accepts_tenant_id_query_alias_for_super_admin(monkeypatch) -> None:
    backend = FakeSecretBackend()
    state = {"is_super_admin": True}
    secrets_controller = _load_patch(monkeypatch, backend, state)
    app = Flask(__name__)

    with app.app_context():
        with app.test_request_context("/?tenant_id=tenant-b"):
            response = secrets_controller.secret_list()

    assert response.status_code == 200
    assert response.get_json()["results"][0]["tenantId"] == "tenant-b"
    assert backend.calls == [
        ("serialize_secret_list_result", 1, 100, "tenant-b"),
    ]
