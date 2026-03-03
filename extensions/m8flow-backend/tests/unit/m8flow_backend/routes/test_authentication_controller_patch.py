from flask import Flask

from m8flow_backend.routes.authentication_controller_patch import (
    _handle_tenant_login_request,
    apply_login_tenant_patch,
)


def test_handle_tenant_login_request_rejects_prefix_trick_redirect_url() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"

    path = "/v1.0/login?tenant=tenant-a&redirect_url=https://app.example.com.evil.com/tasks"
    with app.test_request_context(path=path, method="GET"):
        response, status_code = _handle_tenant_login_request(app)

    assert status_code == 400
    assert response.get_json()["detail"] == "Invalid redirect_url"


def test_apply_login_tenant_patch_is_idempotent(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    calls = {"count": 0}

    def _fake_ensure_realm_identifier_in_auth_configs(_flask_app):
        calls["count"] += 1

    monkeypatch.setattr(
        "m8flow_backend.services.auth_config_service.ensure_realm_identifier_in_auth_configs",
        _fake_ensure_realm_identifier_in_auth_configs,
    )

    apply_login_tenant_patch(app)
    apply_login_tenant_patch(app)

    funcs = app.before_request_funcs.get(None, [])
    marked_handlers = [f for f in funcs if getattr(f, "_m8flow_login_tenant_patch", False)]
    assert len(marked_handlers) == 1
    assert calls["count"] == 1
