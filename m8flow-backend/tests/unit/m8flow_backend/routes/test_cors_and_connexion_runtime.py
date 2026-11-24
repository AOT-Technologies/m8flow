"""CORS at the Connexion ASGI edge + served-object / entrypoint checks.

Preflight OPTIONS and Connexion-layer errors never reach Flask, so CORS must
live on Starlette CORSMiddleware (not flask_cors). These tests go through the
Connexion test client, which is the same ASGI stack uvicorn serves.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from connexion import FlaskApp
from flask import jsonify

from m8flow_backend.api_versioning import current_api_version

_REPO_ROOT = Path(__file__).resolve().parents[5]
_FRONTEND_ORIGIN = "http://localhost:6841"
_DESIGNER_ORIGIN = "http://localhost:6853"
_VITE_ORIGIN = "http://localhost:5173"
_ALLOWED_HEADERS = (
    "authorization",
    "content-type",
    "accept",
    "x-m8flow-tenant-id",
    "x-m8flow-api-version",
)


def _preflight(
    client,
    path,
    *,
    origin,
    request_method="GET",
    request_headers="Authorization, Content-Type, Accept, X-M8Flow-API-Version",
):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": request_method,
            "Access-Control-Request-Headers": request_headers,
        },
    )


def test_preflight_allows_local_ui_origins(client):
    for origin in (_FRONTEND_ORIGIN, _DESIGNER_ORIGIN, _VITE_ORIGIN):
        response = _preflight(client, "/v1.0/ping", origin=origin)
        assert response.status_code == 200, origin
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"
        allowed = {h.strip().lower() for h in response.headers["access-control-allow-headers"].split(",")}
        assert set(_ALLOWED_HEADERS) <= allowed
        assert response.headers["access-control-allow-origin"] != "*"


def test_preflight_rejects_unknown_origin(client):
    response = _preflight(client, "/v1.0/ping", origin="http://evil.example")
    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") != "http://evil.example"


def test_preflight_covers_connexion_operation_path(client):
    response = _preflight(client, "/v1.0/m8flow/ping", origin=_FRONTEND_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _FRONTEND_ORIGIN


@pytest.mark.parametrize("path", ("/v1.0/ping", "/v1.0/m8flow/ping"))
@pytest.mark.parametrize("header_value", ("future", "3.0"))
def test_unsupported_api_version_is_rejected_consistently(client, path, header_value):
    response = client.get(path, headers={"X-M8Flow-API-Version": header_value})

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "unsupported_api_version",
        "message": (
            f"Unsupported X-M8Flow-API-Version value '{header_value}'. "
            "Supported versions: 1.0, 2.0."
        ),
    }
    assert response.headers.get("x-m8flow-api-version") is None
    vary = {value.strip().lower() for value in response.headers["vary"].split(",")}
    assert "x-m8flow-api-version" in vary


def test_duplicate_api_version_headers_are_rejected(client):
    response = client.get(
        "/v1.0/ping",
        headers=[("X-M8Flow-API-Version", "1.0"), ("X-M8Flow-API-Version", "2.0")],
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_api_version_header",
        "message": "X-M8Flow-API-Version must contain exactly one version value.",
    }
    assert response.headers.get("x-m8flow-api-version") is None
    vary = {value.strip().lower() for value in response.headers["vary"].split(",")}
    assert "x-m8flow-api-version" in vary


def test_connexion_error_response_includes_cors_headers(client):
    """Validation fails at the ASGI layer; CORS must still attach to that 400."""
    response = client.get(
        "/v1.0/m8flow/tenant-login-url",
        headers={"Origin": _FRONTEND_ORIGIN, "X-M8Flow-API-Version": "2.0"},
    )
    assert response.status_code == 400
    assert response.headers["access-control-allow-origin"] == _FRONTEND_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["x-m8flow-api-version"] == "2.0"
    vary = {value.strip().lower() for value in response.headers["vary"].split(",")}
    assert "x-m8flow-api-version" in vary


def test_flask_error_response_includes_selected_api_version_and_vary(
    connexion_app, client, monkeypatch
):
    flask_app = connexion_app.app
    path = "/v1.0/ping"
    rule = next(rule for rule in flask_app.url_map.iter_rules() if rule.rule == path)

    def failing_handler():
        return jsonify({"error_code": "test_error", "message": "expected"}), 400

    monkeypatch.setitem(flask_app.view_functions, rule.endpoint, failing_handler)
    response = client.get(
        path,
        headers={"Origin": _FRONTEND_ORIGIN, "X-M8Flow-API-Version": "2.0"},
    )

    assert response.status_code == 400
    assert response.headers["x-m8flow-api-version"] == "2.0"
    vary = {value.strip().lower() for value in response.headers["vary"].split(",")}
    assert {"origin", "x-m8flow-api-version"} <= vary


def test_flask_liveness_response_includes_cors_headers(client):
    response = client.get("/v1.0/ping", headers={"Origin": _FRONTEND_ORIGIN})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _FRONTEND_ORIGIN
    vary = {value.strip().lower() for value in response.headers["vary"].split(",")}
    assert {"origin", "x-m8flow-api-version"} <= vary


def test_response_exposes_selected_api_version_and_varies_by_version(client):
    for path in ("/v1.0/ping", "/v1.0/m8flow/ping"):
        response = client.get(
            path,
            headers={"Origin": _FRONTEND_ORIGIN, "X-M8Flow-API-Version": "2.0"},
        )
        assert response.status_code == 200
        assert response.headers["x-m8flow-api-version"] == "2.0"
        exposed_headers = {
            value.strip().lower()
            for value in response.headers["access-control-expose-headers"].split(",")
        }
        assert "x-m8flow-api-version" in exposed_headers
        vary = {value.strip().lower() for value in response.headers["vary"].split(",")}
        assert "x-m8flow-api-version" in vary


def test_response_defaults_api_version_header_to_v1(client):
    response = client.get("/v1.0/ping")
    assert response.status_code == 200
    assert response.headers["x-m8flow-api-version"] == "1.0"


@pytest.mark.parametrize(("header_value", "expected_version"), ((None, "1.0"), ("2.0", "2.0")))
def test_selected_api_version_is_available_to_flask_route(
    connexion_app, client, monkeypatch, header_value, expected_version
):
    flask_app = connexion_app.app
    path = "/v1.0/ping"
    rule = next(rule for rule in flask_app.url_map.iter_rules() if rule.rule == path)

    def version_echo_handler():
        return jsonify({"api_version": current_api_version().value})

    # Replace the Flask route function only for this test. Going through the
    # ASGI client still exercises the registered before_request hook.
    monkeypatch.setitem(flask_app.view_functions, rule.endpoint, version_echo_handler)
    headers = {"X-M8Flow-API-Version": header_value} if header_value is not None else {}

    response = client.get(path, headers=headers)

    assert response.status_code == 200
    assert response.get_json() == {"api_version": expected_version}


@pytest.mark.parametrize(("header_value", "expected_version"), ((None, "1.0"), ("2.0", "2.0")))
def test_selected_api_version_is_available_to_connexion_operation(
    db_engine, monkeypatch, header_value, expected_version
):
    from m8flow_backend import observability
    from m8flow_backend.app import create_app

    def version_echo_operation():
        return ({"api_version": current_api_version().value}, 200)

    # Connexion resolves operationId during add_api(), so replace the health
    # operation before creating the app. The request still crosses Connexion's
    # ASGI router and Flask's registered before_request hooks.
    monkeypatch.setattr(observability.health, "health_check", version_echo_operation)
    application = create_app()
    client = application.test_client(follow_redirects=False)
    headers = {"X-M8Flow-API-Version": header_value} if header_value is not None else {}

    response = client.get("/v1.0/m8flow/ping", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"api_version": expected_version}


def test_env_origin_is_additive(db_engine, monkeypatch):
    extra = "http://localhost:9999"
    monkeypatch.setenv("M8FLOW_BACKEND_CORS_ALLOW_ORIGINS", extra)
    from m8flow_backend.app import create_app

    application = create_app()
    raw = application.test_client(follow_redirects=False)
    response = raw.options(
        "/v1.0/ping",
        headers={
            "Origin": extra,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == extra

    still_default = raw.options(
        "/v1.0/ping",
        headers={
            "Origin": _FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert still_default.status_code == 200
    assert still_default.headers["access-control-allow-origin"] == _FRONTEND_ORIGIN


def test_create_app_returns_connexion_asgi_flask_app(connexion_app):
    assert isinstance(connexion_app, FlaskApp)
    assert callable(connexion_app)


def test_entrypoint_serves_connexion_asgi_without_wsgi_interface():
    # Comments may mention the historical drop; uvicorn must not actually get the flag.
    for rel in (
        "m8flow-backend/bin/run_m8flow_backend.sh",
        "m8flow-backend/bin/run_m8flow_backend.ps1",
    ):
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "m8flow_backend.app:app" in text
        assert not re.search(r"(?<!no )--interface\s+wsgi", text)


def test_served_host_paths_respond(client):
    assert client.get("/").status_code == 200
    for path in ("/v1.0/status", "/v1.0/ping", "/v1.0/healthy", "/v1.0/readyz"):
        assert client.get(path).status_code == 200, path

    ping = client.get("/v1.0/m8flow/ping")
    assert ping.status_code == 200
    assert ping.get_json().get("ok") is True or ping.get_json().get("status") == "ok"

    spec = client.get("/v1.0/m8flow/openapi.json")
    assert spec.status_code == 200
    body = spec.get_json()
    assert body.get("openapi") or body.get("swagger")
    version_parameters = body["paths"]["/ping"].get("parameters", [])
    assert any(
        parameter.get("name") == "X-M8Flow-API-Version"
        and parameter.get("in") == "header"
        and parameter.get("required") is False
        for parameter in version_parameters
    )

    ui = client.get("/v1.0/m8flow/ui")
    assert ui.status_code in {200, 307, 308}
    ui_slash = client.get("/v1.0/m8flow/ui/")
    assert ui_slash.status_code == 200
    assert "html" in (ui_slash.headers.get("content-type") or "").lower()
