# m8flow-backend/tests/unit/m8flow_backend/routes/test_root_controller.py
from __future__ import annotations

from flask import Flask

import m8flow_backend.services.tenant_context_middleware as tenant_context_middleware
from m8flow_backend.routes.root_controller import root
from m8flow_backend.startup.routes import register_root_route
from m8flow_backend.startup.tenant_resolution import register_tenant_resolution_after_auth

BROWSER_ACCEPT_HEADER = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_root_route(app)
    return app


def test_root_returns_html_landing_page_for_browsers() -> None:
    app = _make_app()

    response = app.test_client().get("/", headers={"Accept": BROWSER_ACCEPT_HEADER})

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert "/v1.0/ui/" in body
    assert "/v1.0/ping" in body
    assert "Swagger UI" in body
    assert "tenant_required" not in body


def test_root_returns_json_info_for_api_clients() -> None:
    app = _make_app()

    response = app.test_client().get("/", headers={"Accept": "application/json"})

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    payload = response.get_json()
    assert payload["docs"] == "/v1.0/ui/"
    assert payload["health"] == "/v1.0/ping"
    assert payload["openapi"] == "/v1.0/openapi.json"
    assert payload["status"] == "/v1.0/status"


def test_root_returns_json_for_wildcard_accept() -> None:
    # curl and most scripts send Accept: */* and must get JSON, not HTML.
    app = _make_app()

    response = app.test_client().get("/", headers={"Accept": "*/*"})

    assert response.status_code == 200
    assert response.mimetype == "application/json"


def test_root_honors_configured_api_path_prefix() -> None:
    app = _make_app()
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v2.0"

    response = app.test_client().get("/", headers={"Accept": "application/json"})

    assert response.get_json()["docs"] == "/v2.0/ui/"


def test_root_rejects_non_get_methods() -> None:
    app = _make_app()

    response = app.test_client().post("/")

    assert response.status_code == 405


def test_root_view_is_marked_tenant_context_exempt() -> None:
    assert getattr(root, "_m8flow_sets_tenant_context", False) is True


def test_tenant_resolution_skips_root_but_still_guards_other_paths(monkeypatch) -> None:
    app = _make_app()

    @app.route("/v1.0/needs-tenant")
    def needs_tenant() -> dict:
        return {"ok": True}

    resolver_calls: list[str] = []

    def fake_resolve_request_tenant() -> None:
        from flask import request

        resolver_calls.append(request.path)

    monkeypatch.setattr(tenant_context_middleware, "resolve_request_tenant", fake_resolve_request_tenant)
    register_tenant_resolution_after_auth(app)

    client = app.test_client()

    root_response = client.get("/", headers={"Accept": BROWSER_ACCEPT_HEADER})
    assert root_response.status_code == 200
    assert resolver_calls == []

    other_response = client.get("/v1.0/needs-tenant")
    assert other_response.status_code == 200
    assert resolver_calls == ["/v1.0/needs-tenant"]


def test_register_root_route_registers_wsgi_prefixed_variant(monkeypatch) -> None:
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_WSGI_PATH_PREFIX", "/api")
    app = Flask(__name__)
    app.config["TESTING"] = True

    register_root_route(app)

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/" in rules
    assert "/api/" in rules

    response = app.test_client().get("/api/", headers={"Accept": "application/json"})
    assert response.status_code == 200
    assert response.get_json()["docs"] == "/v1.0/ui/"


def test_register_root_route_normalizes_prefix_without_leading_slash(monkeypatch) -> None:
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_WSGI_PATH_PREFIX", "api")
    app = Flask(__name__)
    app.config["TESTING"] = True

    register_root_route(app)

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/" in rules


def test_register_root_route_skips_prefix_variant_for_root_like_prefixes(monkeypatch) -> None:
    for degenerate_prefix in ("/", "//", "   ", "  /  "):
        monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_WSGI_PATH_PREFIX", degenerate_prefix)
        app = Flask(__name__)
        app.config["TESTING"] = True

        register_root_route(app)

        assert "m8flow_root" in app.view_functions
        assert "m8flow_root_prefixed" not in app.view_functions


def test_register_root_route_is_idempotent() -> None:
    app = _make_app()

    # Second registration must not raise even though the endpoint already exists.
    register_root_route(app)

    response = app.test_client().get("/", headers={"Accept": "application/json"})
    assert response.status_code == 200
