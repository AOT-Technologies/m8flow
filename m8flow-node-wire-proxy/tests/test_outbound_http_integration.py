# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
"""HTTP V2 service-task calls, end to end over a real socket.

The other adapter tests stub the connector. These send each request through
the /v1/do route, the real http_generic connector and httpx to a local server,
so they cover what a service task actually gets back: status, parsed body,
error envelope, retries, and whether an HTTPS server's certificate is trusted.

The connector refuses loopback destinations (SSRF guard). The ``loopback_allowed``
fixture opens loopback only; every other blocked range stays blocked.
"""

from __future__ import annotations

import base64
import datetime
import ipaddress
import json
import ssl
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import certifi
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from m8flow_node_wire_proxy.app import app
from m8flow_node_wire_proxy.node_wire_gateway import get_http_generic_connector


@dataclass
class Upstream:
    """A local API the service task calls; records what it received."""

    base_url: str
    received: list[dict[str, Any]] = field(default_factory=list)
    # Status codes to answer /flaky with, consumed one per request.
    flaky_statuses: list[int] = field(default_factory=list)


def _handler_for(upstream: Upstream) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def _record(self, body: bytes) -> None:
            parts = urlsplit(self.path)
            upstream.received.append(
                {
                    "method": self.command,
                    "path": parts.path,
                    "query": parse_qs(parts.query),
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": body,
                }
            )

        def _reply(self, status: int, payload: Any = None, content_type: str = "application/json") -> None:
            raw = b"" if payload is None else (payload if isinstance(payload, bytes) else json.dumps(payload).encode())
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("X-Upstream", "m8flow-test")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(raw)

        def _route(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            self._record(body)
            path = urlsplit(self.path).path
            if path == "/orders" and self.command == "GET":
                self._reply(200, {"orders": [{"id": 1, "status": "open"}]})
            elif path == "/orders" and self.command == "POST":
                self._reply(201, {"created": json.loads(body or b"null")})
            elif path == "/orders" and self.command == "HEAD":
                self._reply(200)
            elif path == "/flaky":
                status = upstream.flaky_statuses.pop(0) if upstream.flaky_statuses else 200
                self._reply(status, {"status": status})
            elif path == "/plain":
                self._reply(200, b"not json", content_type="text/plain")
            else:
                self._reply(404, {"detail": "no such resource"})

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _route

    return Handler


def _serve(upstream_scheme: str, ssl_context: ssl.SSLContext | None) -> Iterator[Upstream]:
    upstream = Upstream(base_url="")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(upstream))
    if ssl_context is not None:
        server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    upstream.base_url = f"{upstream_scheme}://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield upstream
    finally:
        server.shutdown()
        server.server_close()


@dataclass
class _Issuer:
    cert_pem: bytes
    server_cert_pem: bytes
    server_key_pem: bytes


def _issue_server_cert(common_name: str) -> _Issuer:
    """A throwaway CA and a 127.0.0.1 server certificate it signed."""
    now = datetime.datetime.now(datetime.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = ec.generate_private_key(ec.SECP256R1())
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return _Issuer(
        cert_pem=ca_cert.public_bytes(serialization.Encoding.PEM),
        server_cert_pem=server_cert.public_bytes(serialization.Encoding.PEM),
        server_key_pem=server_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
    )


@pytest.fixture
def loopback_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the SSRF guard pass 127.0.0.1 so a local server can stand in for an API."""
    get_http_generic_connector()  # imports node-wire with the allowlist set
    import node_wire_http_generic.logic as connector_logic
    import node_wire_http_generic.schema as connector_schema

    for module in (connector_logic, connector_schema):
        guard = module.is_blocked_ip

        def allow_loopback(ip: Any, *args: Any, _guard: Any = guard, **kwargs: Any) -> bool:
            try:
                if ipaddress.ip_address(str(ip)).is_loopback:
                    return False
            except ValueError:
                pass
            return _guard(ip, *args, **kwargs)

        monkeypatch.setattr(module, "is_blocked_ip", allow_loopback)


@pytest.fixture
def client(loopback_allowed: None) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def api() -> Iterator[Upstream]:
    yield from _serve("http", None)


@pytest.fixture
def https_issuer() -> _Issuer:
    return _issue_server_cert("m8flow test CA")


@pytest.fixture
def https_api(https_issuer: _Issuer, tmp_path: Path) -> Iterator[Upstream]:
    cert_file = tmp_path / "server.pem"
    cert_file.write_bytes(https_issuer.server_cert_pem + https_issuer.server_key_pem)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file)
    yield from _serve("https", context)


@pytest.fixture
def ca_in_trust_store(https_issuer: _Issuer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Add the test CA to the bundle outbound calls trust, alongside the public CAs."""
    bundle = tmp_path / "ca-bundle.pem"
    bundle.write_bytes(Path(certifi.where()).read_bytes() + b"\n" + https_issuer.cert_pem)
    monkeypatch.setattr(certifi, "where", lambda: str(bundle))
    # httpx < 0.28 resolves the certifi path once, at import.
    import httpx._config

    ssl_config = getattr(httpx._config, "SSLConfig", None)
    if ssl_config is not None and hasattr(ssl_config, "DEFAULT_CA_BUNDLE_PATH"):
        monkeypatch.setattr(ssl_config, "DEFAULT_CA_BUNDLE_PATH", bundle)


def _do(client: TestClient, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(f"/v1/do/http/{command}", json=payload)
    # The route always answers 200; the outcome is in the envelope.
    assert response.status_code == 200
    return response.json()


def test_get_returns_the_api_json_to_the_service_task(client: TestClient, api: Upstream) -> None:
    envelope = _do(
        client,
        "GetRequestV2",
        {
            "url": f"{api.base_url}/orders",
            "params": {"status": "open"},
            "headers": {"X-Request-Id": "abc-123"},
            "spiff__task_data": {"secret": "must not leave m8flow"},
        },
    )

    assert envelope["error"] is None
    assert envelope["command_response"]["http_status"] == 200
    assert envelope["command_response"]["body"] == {"orders": [{"id": 1, "status": "open"}]}
    [request] = api.received
    assert request["method"] == "GET"
    assert request["query"] == {"status": ["open"]}
    assert request["headers"]["x-request-id"] == "abc-123"
    assert b"must not leave m8flow" not in request["body"]
    assert not any("spiff" in name for name in request["headers"])


def test_post_sends_the_task_data_as_json(client: TestClient, api: Upstream) -> None:
    envelope = _do(
        client,
        "PostRequestV2",
        {"url": f"{api.base_url}/orders", "data": {"item": "laptop", "qty": 2}},
    )

    assert envelope["error"] is None
    assert envelope["command_response"]["http_status"] == 201
    assert envelope["command_response"]["body"] == {"created": {"item": "laptop", "qty": 2}}
    [request] = api.received
    assert request["method"] == "POST"
    assert json.loads(request["body"]) == {"item": "laptop", "qty": 2}


def test_basic_auth_credentials_reach_the_api(client: TestClient, api: Upstream) -> None:
    _do(
        client,
        "GetRequestV2",
        {"url": f"{api.base_url}/orders", "basic_auth_username": "svc", "basic_auth_password": "p@ss"},
    )

    [request] = api.received
    assert request["headers"]["authorization"] == "Basic " + base64.b64encode(b"svc:p@ss").decode()


def test_head_returns_the_status_without_a_body(client: TestClient, api: Upstream) -> None:
    envelope = _do(client, "HeadRequestV2", {"url": f"{api.base_url}/orders"})

    assert envelope["error"] is None
    assert envelope["command_response"]["http_status"] == 200
    [request] = api.received
    assert request["method"] == "HEAD"


def test_non_json_response_is_handed_back_raw(client: TestClient, api: Upstream) -> None:
    envelope = _do(client, "GetRequestV2", {"url": f"{api.base_url}/plain"})

    assert envelope["error"] is None
    assert envelope["command_response"]["body"] == {"raw_response": "not json"}


def test_api_error_status_becomes_a_task_error(client: TestClient, api: Upstream) -> None:
    envelope = _do(client, "GetRequestV2", {"url": f"{api.base_url}/does-not-exist"})

    assert envelope["command_response"]["http_status"] == 404
    assert envelope["error"]["error_code"] == "HttpError404"
    assert "no such resource" in envelope["error"]["message"]


def test_get_retries_a_server_error_and_returns_the_recovered_response(client: TestClient, api: Upstream) -> None:
    api.flaky_statuses = [503, 200]

    envelope = _do(client, "GetRequestV2", {"url": f"{api.base_url}/flaky", "attempts": 2})

    assert envelope["error"] is None
    assert envelope["command_response"]["http_status"] == 200
    assert [r["path"] for r in api.received] == ["/flaky", "/flaky"]


def test_post_is_never_retried(client: TestClient, api: Upstream) -> None:
    api.flaky_statuses = [503, 200]

    envelope = _do(client, "PostRequestV2", {"url": f"{api.base_url}/flaky", "data": {}, "attempts": 2})

    assert envelope["command_response"]["http_status"] == 503
    assert envelope["error"]["error_code"] == "HttpError503"
    assert len(api.received) == 1


@pytest.mark.parametrize("command", ["GetRequestV2", "HeadRequestV2"])
def test_https_api_with_a_trusted_certificate_succeeds(
    client: TestClient, https_api: Upstream, ca_in_trust_store: None, command: str
) -> None:
    envelope = _do(client, command, {"url": f"{https_api.base_url}/orders"})

    assert envelope["error"] is None
    assert envelope["command_response"]["http_status"] == 200
    assert len(https_api.received) == 1


@pytest.mark.parametrize("command", ["GetRequestV2", "PostRequestV2", "HeadRequestV2"])
def test_https_api_with_an_untrusted_certificate_is_refused(
    client: TestClient, https_api: Upstream, command: str
) -> None:
    envelope = _do(client, command, {"url": f"{https_api.base_url}/orders", "data": {"item": "x"}})

    assert envelope["error"] is not None
    assert envelope["command_response"]["http_status"] >= 500
    assert envelope["command_response"]["body"] == {}
    # The TLS handshake failed, so no request (and no task data) reached the server.
    assert https_api.received == []


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
        "http://10.0.0.1/internal",
        "http://192.168.1.1/admin",
    ],
)
@pytest.mark.parametrize("command", ["GetRequestV2", "HeadRequestV2"])
def test_private_network_destinations_stay_blocked(client: TestClient, command: str, url: str) -> None:
    envelope = _do(client, command, {"url": url})

    assert envelope["error"] is not None
    assert envelope["command_response"]["http_status"] == 500
