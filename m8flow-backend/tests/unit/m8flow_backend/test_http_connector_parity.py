"""HTTP-family journeys that must hold together: Connectors, picker, execute.

The host talks to node-wire at POST /v1/do/http/{command}. These tests stub
that proxy (catalog + execute) so execute is the real connector-proxy client,
not a recording fake registered by hand.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from m8flow_bpmn_core.errors import ServiceTaskExecutionError
from m8flow_bpmn_core.services.service_tasks import ServiceTaskContext, ServiceTaskRequest

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.connectors.service import deactivate_profile
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, import_yaml, sync_groups
from m8flow_backend.secrets import add_secret, build_host_service_task_registry
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

_PROFILES = "/v1.0/m8flow/connector-profiles"
_TEMPLATES = "/v1.0/m8flow/connector-templates"
_GROUPED = "/v1.0/m8flow/connectors-grouped"

# Same parameter ids node-wire advertises for GET. Inject only fills names
# the operator declares, so this catalog must include basic_auth_*.
_GET_REQUEST_V2 = {
    "id": "http/GetRequestV2",
    "parameters": [
        {"id": "url", "type": "str", "required": True},
        {"id": "headers", "type": "any", "required": False},
        {"id": "params", "type": "any", "required": False},
        {"id": "basic_auth_username", "type": "str", "required": False},
        {"id": "basic_auth_password", "type": "str", "required": False},
        {"id": "attempts", "type": "int", "required": False},
    ],
}

_OK_ENVELOPE = {
    "command_response": {"body": {"ok": True}, "mimetype": "application/json", "http_status": 200},
    "error": None,
    "command_response_version": 2,
}


class _NodeWireStub(BaseHTTPRequestHandler):
    posts: list[tuple[str, dict]] = []

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/commands":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps([_GET_REQUEST_V2]).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        type(self).posts.append((self.path, payload))
        body = json.dumps(_OK_ENVELOPE).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@pytest.fixture
def node_wire_stub(monkeypatch):
    _NodeWireStub.posts = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _NodeWireStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    url = f"http://{host}:{port}"
    monkeypatch.setenv("M8FLOW_BACKEND_CONNECTOR_PROXY_URL", url)
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_CONNECTOR_PROXY_URL", raising=False)
    try:
        yield _NodeWireStub
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _login_user(client, db_session, *, username: str, groups: list[str], tenant_id: str):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id, name=tenant_id)
    user = ensure_user(
        db_session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=username,
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user, token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bind_session(db_session, monkeypatch) -> None:
    monkeypatch.setattr("m8flow_backend.db.current_session", lambda: db_session)


def _execute(*, parameters, tenant_id="t1"):
    registry = build_host_service_task_registry()
    return registry.execute(
        ServiceTaskRequest(
            operation_id="http/GetRequestV2",
            parameters=parameters,
            context=ServiceTaskContext(tenant_id=tenant_id),
        )
    )


def test_integrator_creates_http_profile_and_execute_posts_auth_without_profile_name(
    client, db_session, monkeypatch, node_wire_stub
):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)

    grouped = client.get(_GROUPED, headers=headers)
    assert grouped.status_code == 200
    http = next(group for group in grouped.get_json() if group["id"] == "http")
    assert http["supportsProfiles"] is True
    assert "http/GetRequestV2" in {op["id"] for op in http["operations"]}

    template = client.get(f"{_TEMPLATES}/http", headers=headers)
    assert template.status_code == 200
    field_ids = {field["id"] for field in template.get_json()["profileFields"]}
    assert field_ids == {"basic_auth_username", "basic_auth_password"}

    created = client.post(
        _PROFILES,
        json={
            "connector_type": "http",
            "profile_name": "http-prod",
            "display_name": "HTTP prod",
            "config": {
                "basic_auth_username": "api-user",
                "basic_auth_password": "from-profile",
            },
        },
        headers=headers,
    )
    assert created.status_code == 201
    body = created.get_json()
    assert "from-profile" not in json.dumps(body)
    assert body["config"] == {}
    assert body["configured_secrets"] == ["basic_auth_password", "basic_auth_username"]

    db_session.expire_all()
    _bind_session(db_session, monkeypatch)
    result = _execute(
        parameters={
            "m8flow_profile": "http-prod",
            "url": "https://example.test/items",
        }
    )
    assert result.payload["command_response"]["http_status"] == 200
    assert node_wire_stub.posts, "execute must POST to the proxy"
    path, posted = node_wire_stub.posts[-1]
    assert path == "/v1/do/http/GetRequestV2"
    assert posted["url"] == "https://example.test/items"
    assert posted["basic_auth_username"] == "api-user"
    assert posted["basic_auth_password"] == "from-profile"
    assert "m8flow_profile" not in posted
    assert "from-profile" not in json.dumps(created.get_json())


def test_editor_cannot_create_profile_and_onboarding_tasks_still_pass(client, db_session):
    _integrator, integrator_token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    created = client.post(
        _PROFILES,
        json={
            "connector_type": "http",
            "profile_name": "http-prod",
            "display_name": "HTTP prod",
            "config": {"basic_auth_username": "api-user", "basic_auth_password": "from-profile"},
        },
        headers=_headers(integrator_token),
    )
    assert created.status_code == 201

    _editor, editor_token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    headers = _headers(editor_token)
    listed = client.get(
        _PROFILES,
        headers=headers,
        query_string={"connector_type": "http", "include_inactive": "false"},
    )
    assert listed.status_code == 200
    rows = listed.get_json()
    assert [row["profile_name"] for row in rows] == ["http-prod"]
    assert "from-profile" not in json.dumps(rows)

    denied = client.post(
        _PROFILES,
        json={
            "connector_type": "http",
            "profile_name": "http-staging",
            "display_name": "Nope",
            "config": {},
        },
        headers=headers,
    )
    assert denied.status_code == 403

    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200


def test_no_profile_still_posts_resolved_secret_sentinel(
    client, db_session, monkeypatch, node_wire_stub
):
    user, _token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    add_secret(
        db_session,
        tenant_id="t1",
        key="API_TOKEN",
        value="sentinel-password",
        user_id=user.id,
    )
    db_session.commit()
    _bind_session(db_session, monkeypatch)

    _execute(
        parameters={
            "url": "https://example.test",
            "basic_auth_password": "M8FLOW_SECRET:API_TOKEN",
        }
    )
    assert node_wire_stub.posts
    _path, posted = node_wire_stub.posts[-1]
    assert posted["basic_auth_password"] == "sentinel-password"
    assert "m8flow_profile" not in posted
    assert "M8FLOW_SECRET:" not in json.dumps(posted)


def test_missing_and_inactive_profile_never_post_to_proxy(
    client, db_session, monkeypatch, node_wire_stub
):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    created = client.post(
        _PROFILES,
        json={
            "connector_type": "http",
            "profile_name": "http-prod",
            "display_name": "HTTP prod",
            "config": {"basic_auth_username": "u", "basic_auth_password": "p"},
        },
        headers=_headers(token),
    )
    profile_id = created.get_json()["id"]
    db_session.expire_all()
    deactivate_profile(db_session, tenant_id="t1", profile_id=profile_id)
    db_session.commit()
    _bind_session(db_session, monkeypatch)

    with pytest.raises(ServiceTaskExecutionError, match="inactive"):
        _execute(parameters={"m8flow_profile": "http-prod", "url": "https://example.test"})
    with pytest.raises(ServiceTaskExecutionError, match="does-not-exist"):
        _execute(parameters={"m8flow_profile": "does-not-exist", "url": "https://example.test"})
    assert node_wire_stub.posts == []
