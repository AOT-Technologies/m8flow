from __future__ import annotations

from flask import Flask

import m8flow_backend.services.tenant_context_middleware as tenant_context_middleware
from m8flow_backend.routes import vault_status_controller
from m8flow_backend.startup.routes import register_vault_status_route
from m8flow_backend.startup.tenant_resolution import register_tenant_resolution_after_auth


def _make_app(*, api_path_prefix: str = "/v1.0") -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = api_path_prefix
    register_vault_status_route(app)
    return app


def test_vault_status_route_returns_healthy_payload(monkeypatch) -> None:
    app = _make_app()

    monkeypatch.setattr(
        vault_status_controller,
        "_vault_status_payload",
        lambda: {
            "enabled": True,
            "configured": True,
            "healthy": True,
            "mount_point": "kv",
            "auth_method": "approle",
        },
    )

    response = app.test_client().get("/v1.0/vault-status")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "enabled": True,
        "configured": True,
        "healthy": True,
        "mount_point": "kv",
        "auth_method": "approle",
    }


def test_vault_status_route_returns_503_when_vault_is_unhealthy(monkeypatch) -> None:
    app = _make_app()

    monkeypatch.setattr(
        vault_status_controller,
        "_vault_status_payload",
        lambda: {
            "enabled": True,
            "configured": True,
            "healthy": False,
            "mount_point": "kv",
            "auth_method": "approle",
        },
    )

    response = app.test_client().get("/v1.0/vault-status")

    assert response.status_code == 503
    assert response.get_json() == {
        "ok": False,
        "enabled": True,
        "configured": True,
        "healthy": False,
        "mount_point": "kv",
        "auth_method": "approle",
    }


def test_register_vault_status_route_honors_api_path_prefix(monkeypatch) -> None:
    app = _make_app(api_path_prefix="/v2.0")

    monkeypatch.setattr(
        vault_status_controller,
        "_vault_status_payload",
        lambda: {
            "enabled": False,
            "configured": False,
            "healthy": None,
        },
    )

    response = app.test_client().get("/v2.0/vault-status")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "enabled": False,
        "configured": False,
        "healthy": None,
    }


def test_vault_status_route_is_public_without_controller_managed_tenant_context() -> None:
    from m8flow_backend.services.authorization_service_patch import M8FLOW_AUTH_EXCLUSION_ADDITIONS

    assert getattr(vault_status_controller.vault_status, "_m8flow_sets_tenant_context", False) is False
    assert "m8flow_backend.routes.vault_status_controller.vault_status" in M8FLOW_AUTH_EXCLUSION_ADDITIONS


def test_tenant_resolution_still_runs_for_vault_status(monkeypatch) -> None:
    app = _make_app()
    resolver_calls: list[str] = []

    monkeypatch.setattr(
        vault_status_controller,
        "_vault_status_payload",
        lambda: {
            "enabled": True,
            "configured": True,
            "healthy": True,
        },
    )

    def fake_resolve_request_tenant() -> None:
        from flask import request

        resolver_calls.append(request.path)

    monkeypatch.setattr(tenant_context_middleware, "resolve_request_tenant", fake_resolve_request_tenant)
    register_tenant_resolution_after_auth(app)

    response = app.test_client().get("/v1.0/vault-status")

    assert response.status_code == 200
    assert resolver_calls == ["/v1.0/vault-status"]
