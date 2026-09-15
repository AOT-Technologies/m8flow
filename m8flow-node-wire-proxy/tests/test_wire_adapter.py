# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from m8flow_node_wire_proxy.adapter import (
    build_http_generic_input,
    envelope_from_http_result,
    execute_http_v2,
    strip_spiff_keys,
)
from m8flow_node_wire_proxy.app import app
from m8flow_node_wire_proxy.catalog import HTTP_V2_COMMANDS, OPERATOR_METHODS


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_catalog_shape(client: TestClient) -> None:
    response = client.get("/v1/commands")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    ids = {entry["id"] for entry in body}
    assert ids == {f"http/{name}" for name in OPERATOR_METHODS}
    for entry in body:
        assert "parameters" in entry
        assert all("id" in p and "type" in p and "required" in p for p in entry["parameters"])
    assert body == HTTP_V2_COMMANDS


def test_strip_spiff_keys() -> None:
    clean = strip_spiff_keys(
        {
            "url": "https://example.com",
            "spiff__task_data": {"a": 1},
            "spiff__callback_url": "http://cb",
            "headers": {"X": "1"},
        }
    )
    assert clean == {"url": "https://example.com", "headers": {"X": "1"}}


@pytest.mark.asyncio
async def test_execute_get_uses_basic_auth_and_ignores_m8flow_profile() -> None:
    mock_run = AsyncMock(return_value=_mock_connector_response(status=200, body='{"ok":true}'))
    with patch("m8flow_node_wire_proxy.adapter._run_http_generic", mock_run):
        result = await execute_http_v2(
            "http",
            "GetRequestV2",
            {
                "url": "https://example.com/items",
                "basic_auth_username": "api-user",
                "basic_auth_password": "from-profile",
                "m8flow_profile": "http-prod",
            },
        )
    assert result["error"] is None
    sent = mock_run.await_args.args[0]
    assert sent["method"] == "GET"
    assert sent["headers"]["Authorization"].startswith("Basic ")
    assert "m8flow_profile" not in sent
    assert "m8flow_profile" not in (sent.get("headers") or {})


def test_build_maps_data_to_body_and_basic_auth() -> None:
    request_input, attempts = build_http_generic_input(
        "PostRequestV2",
        {
            "url": "https://example.com/api",
            "data": {"hello": "world"},
            "basic_auth_username": "u",
            "basic_auth_password": "p",
            "attempts": 99,  # ignored for POST
        },
    )
    assert attempts == 1
    assert request_input["method"] == "POST"
    assert request_input["body"] == {"hello": "world"}
    assert request_input["headers"]["Authorization"].startswith("Basic ")


def test_envelope_parses_json_and_sets_http_error() -> None:
    envelope = envelope_from_http_result(
        status_code=404,
        response_headers={"Content-Type": "application/json"},
        body_text='{"detail":"missing"}',
    )
    assert envelope["command_response_version"] == 2
    assert envelope["command_response"]["http_status"] == 404
    assert envelope["command_response"]["body"] == {"detail": "missing"}
    assert envelope["error"]["error_code"] == "HttpError404"


def _mock_connector_response(*, status: int, body: str, content_type: str = "application/json") -> MagicMock:
    response = MagicMock()
    response.success = True
    response.data = {
        "status_code": status,
        "headers": {"content-type": content_type},
        "body": body,
    }
    response.error_code = None
    response.message = None
    return response


@pytest.mark.asyncio
async def test_execute_get_round_trip() -> None:
    mock_run = AsyncMock(return_value=_mock_connector_response(status=200, body='{"ok":true}'))
    with patch("m8flow_node_wire_proxy.adapter._run_http_generic", mock_run):
        result = await execute_http_v2(
            "http",
            "GetRequestV2",
            {
                "url": "https://example.com/items",
                "params": {"q": "1"},
                "spiff__task_data": {"x": 1},
            },
        )
    assert result["error"] is None
    assert result["command_response"]["body"] == {"ok": True}
    assert result["command_response"]["http_status"] == 200
    sent = mock_run.await_args.args[0]
    assert sent["method"] == "GET"
    assert sent["params"] == {"q": "1"}
    assert "spiff__task_data" not in sent


@pytest.mark.asyncio
async def test_execute_post_round_trip() -> None:
    mock_run = AsyncMock(return_value=_mock_connector_response(status=201, body='{"id":7}'))
    with patch("m8flow_node_wire_proxy.adapter._run_http_generic", mock_run):
        result = await execute_http_v2(
            "http",
            "PostRequestV2",
            {"url": "https://example.com/items", "data": {"name": "n"}},
        )
    assert result["error"] is None
    assert result["command_response"]["body"] == {"id": 7}
    assert result["command_response"]["http_status"] == 201
    sent = mock_run.await_args.args[0]
    assert sent["method"] == "POST"
    assert sent["body"] == {"name": "n"}


def test_do_route_get_via_client(client: TestClient) -> None:
    mock_run = AsyncMock(return_value=_mock_connector_response(status=200, body='{"ping":"pong"}'))
    with patch("m8flow_node_wire_proxy.adapter._run_http_generic", mock_run):
        response = client.post(
            "/v1/do/http/GetRequestV2",
            json={"url": "https://example.com/", "spiff__callback_url": "http://ignored"},
        )
    assert response.status_code == 200
    payload: dict[str, Any] = response.json()
    assert payload["command_response"]["body"] == {"ping": "pong"}
    assert payload["error"] is None


def test_connector_dispatch_table() -> None:
    from m8flow_node_wire_proxy.adapter import _connector_for, _run_head, _run_http_generic

    assert _connector_for("HEAD") is _run_head
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        assert _connector_for(method) is _run_http_generic


@pytest.mark.asyncio
async def test_execute_retries_once_on_5xx_then_succeeds() -> None:
    mock_run = AsyncMock(
        side_effect=[
            _mock_connector_response(status=500, body='{"error":"boom"}'),
            _mock_connector_response(status=200, body='{"ok":true}'),
        ]
    )
    with (
        patch("m8flow_node_wire_proxy.adapter._run_http_generic", mock_run),
        patch("m8flow_node_wire_proxy.adapter.asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        result = await execute_http_v2(
            "http",
            "GetRequestV2",
            {"url": "https://example.com/items", "attempts": 3},
        )
    assert mock_run.await_count == 2
    assert mock_sleep.await_count == 1
    assert result["error"] is None
    assert result["command_response"]["http_status"] == 200


@pytest.mark.asyncio
async def test_execute_does_not_retry_on_4xx() -> None:
    mock_run = AsyncMock(return_value=_mock_connector_response(status=404, body="{}"))
    with (
        patch("m8flow_node_wire_proxy.adapter._run_http_generic", mock_run),
        patch("m8flow_node_wire_proxy.adapter.asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        result = await execute_http_v2(
            "http",
            "GetRequestV2",
            {"url": "https://example.com/items", "attempts": 3},
        )
    assert mock_run.await_count == 1
    assert mock_sleep.await_count == 0
    assert result["command_response"]["http_status"] == 404


@pytest.mark.asyncio
async def test_execute_exhausts_attempts_on_persistent_5xx() -> None:
    mock_run = AsyncMock(return_value=_mock_connector_response(status=503, body="{}"))
    with (
        patch("m8flow_node_wire_proxy.adapter._run_http_generic", mock_run),
        patch("m8flow_node_wire_proxy.adapter.asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        result = await execute_http_v2(
            "http",
            "GetRequestV2",
            {"url": "https://example.com/items", "attempts": 3},
        )
    assert mock_run.await_count == 3
    assert mock_sleep.await_count == 2
    assert result["command_response"]["http_status"] == 503


@pytest.mark.asyncio
async def test_head_fails_closed_when_ssrf_gate_unavailable() -> None:
    """If node_wire_gateway can't provide the SSRF gate, refuse rather than send unchecked."""
    from m8flow_node_wire_proxy.adapter import _run_head

    with patch("m8flow_node_wire_proxy.node_wire_gateway.get_ssrf_gate", return_value=None):
        result = await _run_head({"url": "https://example.com", "headers": {}, "params": None})

    assert result.success is False
    assert result.error_code == "SsrfGateUnavailable"
    assert result.data is None
