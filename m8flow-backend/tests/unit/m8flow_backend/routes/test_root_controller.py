# m8flow-backend/tests/unit/m8flow_backend/routes/test_root_controller.py
from __future__ import annotations

import pytest
from flask import Flask

import m8flow_backend.services.tenant_context_middleware as tenant_context_middleware
from m8flow_backend.routes.root_controller import root
from m8flow_backend.startup.routes import register_root_route
from m8flow_backend.startup.tenant_resolution import (
    _view_function_sets_tenant_context,
    register_tenant_resolution_after_auth,
)

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


@pytest.mark.parametrize(
    ("root_url", "expected_endpoint"),
    [("/", "m8flow_root"), ("/api/", "m8flow_root_prefixed")],
)
def test_root_route_variants_are_excluded_from_auth_identically(
    monkeypatch, root_url, expected_endpoint
) -> None:
    """Near-real auth-layer wiring: both the bare and WSGI-prefixed root URLs must be
    resolved by AuthorizationService to the SAME fully-qualified, auth-excluded function
    and both must skip tenant enforcement. Guards against endpoint-name-based resolution
    causing inconsistent security behavior across equivalent root URLs (PR review).
    """
    from spiffworkflow_backend.services.authorization_service import AuthorizationService

    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_WSGI_PATH_PREFIX", "/api")
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    register_root_route(app)

    with app.app_context():
        # Install the real m8flow auth-exclusion patch (adds root to the exclusion list).
        from m8flow_backend.services import authorization_service_patch

        monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)
        authorization_service_patch.apply()

        # Sanity: the two URLs really are distinct endpoints backed by the same view fn.
        view_function = app.view_functions[expected_endpoint]
        assert view_function is root

        with app.test_request_context(root_url, method="GET"):
            from flask import request

            assert request.endpoint == expected_endpoint

            # Real (un-mocked) resolution must collapse both endpoints to the same path.
            full_path, _module = AuthorizationService.get_fully_qualified_api_function_from_request()
            assert full_path == "m8flow_backend.routes.root_controller.root"
            assert full_path in AuthorizationService.authentication_exclusion_list()

            # Therefore auth is disabled for this request (no auth challenge on either URL).
            assert AuthorizationService.should_disable_auth_for_request() is True

        # And the shared view function is skipped by tenant resolution for both URLs.
        assert _view_function_sets_tenant_context(view_function) is True
