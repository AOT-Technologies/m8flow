from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from m8flow_bpmn_core.errors import ServiceTaskExecutionError
from m8flow_bpmn_core.services.service_tasks import ServiceTaskRegistry

from m8flow_backend.secrets import build_host_service_task_registry, list_connectors

_STUB_CATALOG = [
    {
        "id": "http/GetRequestV2",
        "parameters": [
            {"id": "url", "type": "str", "required": True},
        ],
    },
    {
        "id": "http/PostRequestV2",
        "parameters": [
            {"id": "url", "type": "str", "required": True},
            {"id": "data", "type": "any", "required": False},
        ],
    },
]


class _CatalogHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/commands":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(_STUB_CATALOG).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@pytest.fixture
def stub_connector_proxy():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CatalogHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_build_host_registry_empty_when_url_unset(monkeypatch):
    monkeypatch.delenv("M8FLOW_BACKEND_CONNECTOR_PROXY_URL", raising=False)
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_CONNECTOR_PROXY_URL", raising=False)

    registry = build_host_service_task_registry()

    assert isinstance(registry, ServiceTaskRegistry)
    assert registry.list_commands() == ()
    assert list_connectors(registry) == []


def test_build_host_registry_loads_commands_from_configured_proxy(monkeypatch, stub_connector_proxy):
    monkeypatch.setenv("M8FLOW_BACKEND_CONNECTOR_PROXY_URL", stub_connector_proxy)
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_CONNECTOR_PROXY_URL", raising=False)

    registry = build_host_service_task_registry()
    operation_ids = {cmd.operation_id for cmd in registry.list_commands()}

    assert operation_ids == {"http/GetRequestV2", "http/PostRequestV2"}
    connectors = list_connectors(registry)
    assert connectors == [
        {"name": "http", "commands": ["GetRequestV2", "PostRequestV2"]},
    ]


def test_build_host_registry_fails_clearly_when_proxy_unreachable(monkeypatch):
    monkeypatch.setenv(
        "M8FLOW_BACKEND_CONNECTOR_PROXY_URL",
        "http://127.0.0.1:9",  # discard port — nothing listening
    )
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_CONNECTOR_PROXY_URL", raising=False)

    with pytest.raises(ServiceTaskExecutionError, match="could not reach"):
        build_host_service_task_registry()
