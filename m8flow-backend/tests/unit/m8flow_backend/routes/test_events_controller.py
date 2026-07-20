"""Unit tests for the m8flow-trigger events controller.

The controller authenticates purely from the X-M8FLOW-NATS-API-Key header: the
key resolves the tenant, the owning identity, and the key's scope. No JWT is
involved.

These tests mock the key authentication, the tenant-slug helper, and the NATS
publish so they stay focused on the controller wiring and do not need a database
or a live NATS server.
"""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask

# Setup path for imports (mirror the other route/service tests).
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.routes import events_controller  # noqa: E402
from m8flow_backend.services.nats_token_service import AuthenticatedKey  # noqa: E402

TENANT_ID = "tenant-uuid-1"
TENANT_SLUG = "m8flow"
USERNAME = "ci-pipeline"
API_KEY = "m8f_abc123.secretsecret"


def _make_app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test, no HTTP/CSRF surface
    app.config["SECRET_KEY"] = "test-secret"
    app.add_url_rule(
        "/v1.0/m8flow/events/m8flow-trigger",
        "m8flow_trigger",
        events_controller.m8flow_trigger,
        methods=["POST"],
    )
    return app


def _install_common_mocks(
    monkeypatch,
    *,
    authenticated: AuthenticatedKey | None = None,
) -> dict:
    """Mock the key authentication, tenant-slug helper, and NATS publish.

    Returns a dict capturing the kwargs passed to NatsService.publish_event.
    """
    if authenticated is None:
        authenticated = AuthenticatedKey(
            tenant_id=TENANT_ID, key_id="abc123", created_by=USERNAME, scope=None
        )

    monkeypatch.setattr(
        events_controller.NatsTokenService,
        "authenticate_key",
        staticmethod(lambda raw_key: authenticated),
    )
    monkeypatch.setattr(events_controller, "tenant_slug_for_identifier", lambda tenant_id: TENANT_SLUG)

    captured: dict = {}

    def _publish_event(**kwargs):
        captured.update(kwargs)
        return {
            "id": "event-1",
            "process_instance": {"id": 42, "status": "complete"},
            "api_key": kwargs.get("api_key"),
        }

    monkeypatch.setattr(events_controller.NatsService, "publish_event", staticmethod(_publish_event))
    return captured


def _headers(
    *,
    api_key: str | None = API_KEY,
    process: str | None = None,
    stream: str | None = None,
) -> dict:
    headers = {}
    if api_key is not None:
        headers["X-M8FLOW-NATS-API-Key"] = api_key
    if process is not None:
        headers["X-M8FLOW-Process-Identifier"] = process
    if stream is not None:
        headers["X-M8FLOW-Stream-Name"] = stream
    return headers


def test_valid_key_publishes_with_body_process_identifier(monkeypatch) -> None:
    app = _make_app()
    captured = _install_common_mocks(monkeypatch)

    with app.test_client() as client:
        response = client.post(
            "/v1.0/m8flow/events/m8flow-trigger",
            headers=_headers(),
            json={"processIdentifier": "group-a/flow-a", "data": {"foo": "bar"}},
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["data"]["username"] == USERNAME
    assert body["data"]["tenant_id"] == TENANT_ID
    assert body["data"]["tenant_slug"] == TENANT_SLUG

    # Identity, tenant, and stream name are derived server-side from the key.
    assert captured["username"] == USERNAME
    assert captured["tenant_id"] == TENANT_ID
    assert captured["tenant_slug"] == TENANT_SLUG
    assert captured["process_identifier"] == "group-a/flow-a"
    assert captured["stream_name"] == "M8FLOW_EVENTS"
    # The raw key is still forwarded to the consumer.
    assert captured["api_key"] == API_KEY


def test_process_identifier_header_fallback(monkeypatch) -> None:
    app = _make_app()
    captured = _install_common_mocks(monkeypatch)

    with app.test_client() as client:
        response = client.post(
            "/v1.0/m8flow/events/m8flow-trigger",
            headers=_headers(process="header/flow"),
            json={"data": {}},
        )

    assert response.status_code == 200
    assert captured["process_identifier"] == "header/flow"


def test_missing_api_key_returns_401(monkeypatch) -> None:
    app = _make_app()
    _install_common_mocks(monkeypatch)

    with app.test_client() as client:
        response = client.post(
            "/v1.0/m8flow/events/m8flow-trigger",
            headers=_headers(api_key=None),
            json={"processIdentifier": "g/p", "data": {}},
        )

    assert response.status_code == 401
    assert response.get_json()["error_code"] == "missing_api_key"


def test_invalid_key_returns_403(monkeypatch) -> None:
    app = _make_app()
    _install_common_mocks(monkeypatch)
    monkeypatch.setattr(
        events_controller.NatsTokenService,
        "authenticate_key",
        staticmethod(lambda raw_key: None),
    )

    with app.test_client() as client:
        response = client.post(
            "/v1.0/m8flow/events/m8flow-trigger",
            headers=_headers(),
            json={"processIdentifier": "g/p", "data": {}},
        )

    assert response.status_code == 403
    assert response.get_json()["error_code"] == "invalid_api_key"


def test_missing_process_identifier_returns_400(monkeypatch) -> None:
    app = _make_app()
    _install_common_mocks(monkeypatch)

    with app.test_client() as client:
        response = client.post(
            "/v1.0/m8flow/events/m8flow-trigger",
            headers=_headers(),
            json={"data": {}},
        )

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "missing_process_identifier"


def test_process_out_of_scope_returns_403(monkeypatch) -> None:
    app = _make_app()
    scoped = AuthenticatedKey(
        tenant_id=TENANT_ID, key_id="abc123", created_by=USERNAME, scope="group-a/flow-a"
    )
    _install_common_mocks(monkeypatch, authenticated=scoped)

    with app.test_client() as client:
        response = client.post(
            "/v1.0/m8flow/events/m8flow-trigger",
            headers=_headers(),
            json={"processIdentifier": "group-b/other", "data": {}},
        )

    assert response.status_code == 403
    assert response.get_json()["error_code"] == "process_not_in_scope"


def test_process_in_scope_publishes(monkeypatch) -> None:
    app = _make_app()
    scoped = AuthenticatedKey(
        tenant_id=TENANT_ID, key_id="abc123", created_by=USERNAME, scope="group-a/flow-a,group-a/flow-b"
    )
    captured = _install_common_mocks(monkeypatch, authenticated=scoped)

    with app.test_client() as client:
        response = client.post(
            "/v1.0/m8flow/events/m8flow-trigger",
            headers=_headers(),
            json={"processIdentifier": "group-a/flow-b", "data": {}},
        )

    assert response.status_code == 200
    assert captured["process_identifier"] == "group-a/flow-b"


def test_client_stream_name_header_is_ignored(monkeypatch) -> None:
    """A caller-supplied X-M8FLOW-Stream-Name must never override the configured stream.

    The controller always publishes to nats_events_stream_name(); the header is
    inert, so an attacker cannot redirect events onto an arbitrary stream.
    """
    app = _make_app()
    captured = _install_common_mocks(monkeypatch)

    with app.test_client() as client:
        response = client.post(
            "/v1.0/m8flow/events/m8flow-trigger",
            headers=_headers(stream="attacker-controlled-stream"),
            json={"processIdentifier": "group-a/flow-a", "data": {}},
        )

    assert response.status_code == 200
    # The configured stream is used, not the header value.
    assert captured["stream_name"] == "M8FLOW_EVENTS"
    assert captured["stream_name"] != "attacker-controlled-stream"


def test_unresolvable_tenant_slug_returns_400(monkeypatch) -> None:
    """If the tenant slug cannot be resolved for the key's tenant, return 400."""
    app = _make_app()
    _install_common_mocks(monkeypatch)
    # Override the slug helper to simulate an unresolvable tenant.
    monkeypatch.setattr(
        events_controller, "tenant_slug_for_identifier", lambda tenant_id: None
    )

    with app.test_client() as client:
        response = client.post(
            "/v1.0/m8flow/events/m8flow-trigger",
            headers=_headers(),
            json={"processIdentifier": "group-a/flow-a", "data": {}},
        )

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_slug_unresolved"
