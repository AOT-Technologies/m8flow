from __future__ import annotations

import importlib
import sys
from types import ModuleType
from pathlib import Path

from flask import Flask
from flask import g


SRC_DIR = Path(__file__).resolve().parents[5] / "m8flow-backend" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def test_health_controller_patch_resolves_tenant_before_status(monkeypatch) -> None:
    call_state: dict[str, object] = {}

    fake_tenant_context_module = ModuleType("m8flow_backend.services.tenant_context_middleware")

    def fake_resolve_request_tenant() -> None:
        call_state["resolve_request_tenant_called"] = True
        g.m8flow_tenant_id = "tenant-a"

    fake_tenant_context_module.resolve_request_tenant = fake_resolve_request_tenant

    fake_authentication_controller_module = ModuleType("spiffworkflow_backend.routes.authentication_controller")

    def fake_verify_token(*_args, **_kwargs):
        call_state["verify_token_called"] = True
        g.user = type("User", (), {"id": 9, "username": "admin"})()
        return {"sub": "subject-123"}

    fake_authentication_controller_module.verify_token = fake_verify_token

    fake_authorization_service_module = ModuleType("spiffworkflow_backend.services.authorization_service")

    class FakeAuthorizationService:
        @classmethod
        def user_has_permission(cls, user, permission, target_uri):
            call_state["user_seen_by_permission_check"] = getattr(user, "username", None)
            call_state["tenant_seen_by_permission_check"] = getattr(g, "m8flow_tenant_id", None)
            call_state["permission_target"] = target_uri
            return getattr(g, "m8flow_tenant_id", None) == "tenant-a"

        @classmethod
        def create_user_from_sign_in(cls, decoded_token):
            call_state["create_user_from_sign_in_called"] = decoded_token
            return type("User", (), {"id": 10, "username": "synced-admin"})()

    fake_authorization_service_module.AuthorizationService = FakeAuthorizationService

    fake_process_instance_module = ModuleType("spiffworkflow_backend.models.process_instance")

    class _FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            call_state["process_instance_query_called"] = True
            return None

    class FakeProcessInstanceModel:
        query = _FakeQuery()

    fake_process_instance_module.ProcessInstanceModel = FakeProcessInstanceModel

    fake_health_controller_module = ModuleType("spiffworkflow_backend.routes.health_controller")

    def fake_status():
        return {"ok": False, "can_access_frontend": False}, 500

    fake_status.__module__ = fake_health_controller_module.__name__
    fake_status.__name__ = "status"
    fake_health_controller_module.status = fake_status

    fake_spiffworkflow_backend_module = ModuleType("spiffworkflow_backend")
    fake_spiffworkflow_backend_module.__path__ = []
    fake_spiffworkflow_backend_routes_module = ModuleType("spiffworkflow_backend.routes")
    fake_spiffworkflow_backend_routes_module.__path__ = []
    fake_spiffworkflow_backend_services_module = ModuleType("spiffworkflow_backend.services")
    fake_spiffworkflow_backend_services_module.__path__ = []
    fake_spiffworkflow_backend_models_module = ModuleType("spiffworkflow_backend.models")
    fake_spiffworkflow_backend_models_module.__path__ = []
    fake_m8flow_services_module = ModuleType("m8flow_backend.services")
    fake_m8flow_services_module.__path__ = []
    fake_tenant_identity_helpers_module = ModuleType("m8flow_backend.services.tenant_identity_helpers")

    def fake_tenant_id_from_payload(payload):
        if isinstance(payload, dict):
            return payload.get("m8flow_tenant_id")
        return None

    fake_tenant_identity_helpers_module.tenant_id_from_payload = fake_tenant_id_from_payload

    monkeypatch.setitem(sys.modules, "m8flow_backend.services", fake_m8flow_services_module)
    monkeypatch.setitem(sys.modules, "m8flow_backend.services.tenant_context_middleware", fake_tenant_context_module)
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.tenant_identity_helpers",
        fake_tenant_identity_helpers_module,
    )
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend", fake_spiffworkflow_backend_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes", fake_spiffworkflow_backend_routes_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services", fake_spiffworkflow_backend_services_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models", fake_spiffworkflow_backend_models_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.authentication_controller",
        fake_authentication_controller_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.health_controller",
        fake_health_controller_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.authorization_service",
        fake_authorization_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.process_instance",
        fake_process_instance_module,
    )

    sys.modules.pop("m8flow_backend.routes.health_controller_patch", None)
    health_controller_patch = importlib.import_module("m8flow_backend.routes.health_controller_patch")
    monkeypatch.setattr(health_controller_patch, "_PATCHED", False)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.add_url_rule(
        "/v1.0/status",
        endpoint="spiffworkflow_backend.routes.health_controller.status",
        view_func=fake_status,
        methods=["GET"],
    )

    health_controller_patch.apply(app)

    response = app.test_client().get("/v1.0/status")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}
    assert call_state["resolve_request_tenant_called"] is True
    assert call_state["process_instance_query_called"] is True
    assert call_state["verify_token_called"] is True
    assert call_state["user_seen_by_permission_check"] == "admin"
    assert call_state["tenant_seen_by_permission_check"] == "tenant-a"
    assert call_state["permission_target"] == "/frontend-access"
    assert app.view_functions["spiffworkflow_backend.routes.health_controller.status"].__module__ == (
        "spiffworkflow_backend.routes.health_controller"
    )
    assert app.view_functions["spiffworkflow_backend.routes.health_controller.status"].__name__ == "status"


def test_health_controller_patch_synchronizes_selected_org_when_multi_org_token_cannot_resolve_tenant(
    monkeypatch,
) -> None:
    call_state: dict[str, object] = {}

    fake_tenant_context_module = ModuleType("m8flow_backend.services.tenant_context_middleware")

    def fake_resolve_request_tenant() -> None:
        g._m8flow_decoded_token = {
            "iss": "http://localhost:7002/realms/m8flow",
            "preferred_username": "admin",
            "organization": {
                "it": {"id": "tenant-it", "groups": ["/tenant-admin"]},
                "m8flow": {"id": "tenant-default", "groups": ["/tenant-admin"]},
            },
        }
        raise RuntimeError("tenant_required")

    fake_tenant_context_module.resolve_request_tenant = fake_resolve_request_tenant

    fake_authentication_controller_module = ModuleType("spiffworkflow_backend.routes.authentication_controller")

    def fake_verify_token(*_args, **_kwargs):
        raise RuntimeError("invalid_token")

    fake_authentication_controller_module.verify_token = fake_verify_token

    fake_authorization_service_module = ModuleType("spiffworkflow_backend.services.authorization_service")

    class FakeAuthorizationService:
        @classmethod
        def user_has_permission(cls, user, permission, target_uri):
            call_state["permission_user"] = getattr(user, "username", None)
            call_state["permission_tenant"] = getattr(g, "m8flow_tenant_id", None)
            return (
                getattr(user, "username", None) == "synced-admin"
                and getattr(g, "m8flow_tenant_id", None) == "tenant-it"
                and target_uri == "/frontend-access"
            )

        @classmethod
        def create_user_from_sign_in(cls, decoded_token):
            call_state["synced_token"] = decoded_token
            return type("User", (), {"id": 10, "username": "synced-admin"})()

    fake_authorization_service_module.AuthorizationService = FakeAuthorizationService

    fake_process_instance_module = ModuleType("spiffworkflow_backend.models.process_instance")

    class _FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

    class FakeProcessInstanceModel:
        query = _FakeQuery()

    fake_process_instance_module.ProcessInstanceModel = FakeProcessInstanceModel

    fake_health_controller_module = ModuleType("spiffworkflow_backend.routes.health_controller")

    def fake_status():
        return {"ok": False, "can_access_frontend": False}, 500

    fake_status.__module__ = fake_health_controller_module.__name__
    fake_status.__name__ = "status"
    fake_health_controller_module.status = fake_status

    fake_spiffworkflow_backend_module = ModuleType("spiffworkflow_backend")
    fake_spiffworkflow_backend_module.__path__ = []
    fake_spiffworkflow_backend_routes_module = ModuleType("spiffworkflow_backend.routes")
    fake_spiffworkflow_backend_routes_module.__path__ = []
    fake_spiffworkflow_backend_services_module = ModuleType("spiffworkflow_backend.services")
    fake_spiffworkflow_backend_services_module.__path__ = []
    fake_spiffworkflow_backend_models_module = ModuleType("spiffworkflow_backend.models")
    fake_spiffworkflow_backend_models_module.__path__ = []
    fake_m8flow_services_module = ModuleType("m8flow_backend.services")
    fake_m8flow_services_module.__path__ = []
    fake_tenant_identity_helpers_module = ModuleType("m8flow_backend.services.tenant_identity_helpers")

    def fake_tenant_id_from_payload(payload):
        if isinstance(payload, dict):
            return payload.get("m8flow_tenant_id")
        return None

    fake_tenant_identity_helpers_module.tenant_id_from_payload = fake_tenant_id_from_payload

    monkeypatch.setitem(sys.modules, "m8flow_backend.services", fake_m8flow_services_module)
    monkeypatch.setitem(sys.modules, "m8flow_backend.services.tenant_context_middleware", fake_tenant_context_module)
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.tenant_identity_helpers",
        fake_tenant_identity_helpers_module,
    )
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend", fake_spiffworkflow_backend_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.routes", fake_spiffworkflow_backend_routes_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services", fake_spiffworkflow_backend_services_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models", fake_spiffworkflow_backend_models_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.authentication_controller",
        fake_authentication_controller_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.routes.health_controller",
        fake_health_controller_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.authorization_service",
        fake_authorization_service_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.process_instance",
        fake_process_instance_module,
    )

    sys.modules.pop("m8flow_backend.routes.health_controller_patch", None)
    health_controller_patch = importlib.import_module("m8flow_backend.routes.health_controller_patch")
    monkeypatch.setattr(health_controller_patch, "_PATCHED", False)
    monkeypatch.setattr(health_controller_patch, "_canonical_tenant_id_for_status", lambda tenant_identifier: tenant_identifier)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.add_url_rule(
        "/v1.0/status",
        endpoint="spiffworkflow_backend.routes.health_controller.status",
        view_func=fake_status,
        methods=["GET"],
    )

    health_controller_patch.apply(app)

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")
    client.set_cookie("m8flow_selected_tenant", "tenant-it")
    response = client.get("/v1.0/status")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "can_access_frontend": True}
    assert call_state["permission_user"] == "synced-admin"
    assert call_state["permission_tenant"] == "tenant-it"
    assert call_state["synced_token"] == {
        "iss": "http://localhost:7002/realms/m8flow",
        "preferred_username": "admin",
        "organization": {
            "it": {"id": "tenant-it", "groups": ["/tenant-admin"]},
        },
        "m8flow_tenant_id": "tenant-it",
        "m8flow_tenant_alias": "it",
    }
