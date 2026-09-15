"""CORS at the Connexion ASGI edge + served-object / entrypoint checks.

Preflight OPTIONS and Connexion-layer errors never reach Flask, so CORS must
live on Starlette CORSMiddleware (not flask_cors). These tests go through the
Connexion test client, which is the same ASGI stack uvicorn serves.
"""

from __future__ import annotations

import re
from pathlib import Path

from connexion import FlaskApp

_REPO_ROOT = Path(__file__).resolve().parents[5]
_FRONTEND_ORIGIN = "http://localhost:6841"
_DESIGNER_ORIGIN = "http://localhost:6853"
_VITE_ORIGIN = "http://localhost:5173"
_ALLOWED_HEADERS = ("authorization", "content-type", "accept", "x-m8flow-tenant-id")


def _preflight(client, path, *, origin, request_method="GET", request_headers="Authorization, Content-Type, Accept"):
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


def test_connexion_error_response_includes_cors_headers(client):
    """Validation fails at the ASGI layer; CORS must still attach to that 400."""
    response = client.get(
        "/v1.0/m8flow/tenant-login-url",
        headers={"Origin": _FRONTEND_ORIGIN},
    )
    assert response.status_code == 400
    assert response.headers["access-control-allow-origin"] == _FRONTEND_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_flask_liveness_response_includes_cors_headers(client):
    response = client.get("/v1.0/ping", headers={"Origin": _FRONTEND_ORIGIN})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _FRONTEND_ORIGIN


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

    ui = client.get("/v1.0/m8flow/ui")
    assert ui.status_code in {200, 307, 308}
    ui_slash = client.get("/v1.0/m8flow/ui/")
    assert ui_slash.status_code == 200
    assert "html" in (ui_slash.headers.get("content-type") or "").lower()
