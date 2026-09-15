# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from m8flow_backend.connectors.proxy_auth import (
    API_KEY_ENV,
    API_KEY_HEADER,
    install_connector_proxy_client_auth,
)


class _CaptureHandler(BaseHTTPRequestHandler):
    last_headers: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802
        type(self).last_headers = {k: v for k, v in self.headers.items()}
        body = b"[]"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@pytest.fixture
def capture_server():
    _CaptureHandler.last_headers = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_install_connector_proxy_client_auth_sends_header(monkeypatch, capture_server):
    monkeypatch.setenv(API_KEY_ENV, "unit-test-proxy-key")
    install_connector_proxy_client_auth()

    from m8flow_bpmn_core.services.connector_proxy_service_tasks import (
        fetch_connector_proxy_command_definitions,
    )

    fetch_connector_proxy_command_definitions(capture_server)
    assert any(
        k.lower() == API_KEY_HEADER.lower() and v == "unit-test-proxy-key"
        for k, v in _CaptureHandler.last_headers.items()
    )


def test_install_noop_without_key(monkeypatch, capture_server):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    install_connector_proxy_client_auth()

    from m8flow_bpmn_core.services.connector_proxy_service_tasks import (
        fetch_connector_proxy_command_definitions,
    )

    fetch_connector_proxy_command_definitions(capture_server)
    assert not any(k.lower() == API_KEY_HEADER.lower() for k in _CaptureHandler.last_headers)
