# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from m8flow_node_wire_proxy.adapter import (
    build_http_generic_input,
    build_m8flow_input,
    envelope_from_connector_response,
    envelope_from_http_result,
    execute_http_v2,
    execute_m8flow,
    strip_spiff_keys,
)
from m8flow_node_wire_proxy.app import app
from m8flow_node_wire_proxy.catalog import (
    HTTP_V2_COMMANDS,
    M8FLOW_ACTIONS,
    M8FLOW_COMMANDS,
    M8FLOW_CONNECTOR_IDS,
    M8FLOW_PARAM_NAMES,
    OPERATOR_METHODS,
)


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
    assert {f"http/{name}" for name in OPERATOR_METHODS} <= ids
    assert set(M8FLOW_ACTIONS) <= ids
    for entry in body:
        assert "parameters" in entry
        assert all("id" in p and "type" in p and "required" in p for p in entry["parameters"])
    assert body == [*HTTP_V2_COMMANDS, *M8FLOW_COMMANDS]


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


# --- m8flow connectors -----------------------------------------------------


def test_every_catalogued_m8flow_command_maps_to_an_action_and_connector() -> None:
    """A command the catalogue lists but nothing can execute would 500 at runtime."""
    assert {entry["id"] for entry in M8FLOW_COMMANDS} == set(M8FLOW_ACTIONS)
    for command_id in M8FLOW_ACTIONS:
        assert command_id.split("/")[0] in M8FLOW_CONNECTOR_IDS
        assert M8FLOW_PARAM_NAMES[command_id]


def test_build_input_keeps_declared_parameters_and_adds_the_action() -> None:
    request_input = build_m8flow_input(
        "github/ListBranches",
        {"token": "t", "owner": "o", "repo": "r", "per_page": 50},
    )
    assert request_input == {
        "action": "list_branches",
        "token": "t",
        "owner": "o",
        "repo": "r",
        "per_page": 50,
    }


def test_build_input_drops_undeclared_and_blank_values() -> None:
    """Models set extra="forbid", and an unfilled operator param arrives as ""."""
    request_input = build_m8flow_input(
        "github/ConnectRepository",
        {"token": "t", "owner": "o", "repo": "r", "not_a_field": "x", "protected": "", "page": None},
    )
    assert request_input == {"action": "connect_repository", "token": "t", "owner": "o", "repo": "r"}


def test_build_input_strips_spiff_and_profile_keys_end_to_end() -> None:
    request_input = build_m8flow_input(
        "smtp/SendEmail",
        strip_spiff_keys(
            {
                "spiff__task_data": {"x": 1},
                "m8flow_profile": "prod",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "email_from": "a@b.c",
                "email_to": "d@e.f",
                "email_subject": "s",
                "email_body": "b",
            }
        ),
    )
    assert "spiff__task_data" not in request_input
    assert "m8flow_profile" not in request_input
    assert request_input["action"] == "send_email"
    assert request_input["smtp_port"] == 587


def test_envelope_maps_a_successful_response_into_the_body() -> None:
    response = MagicMock(success=True, data={"status_code": 201, "record_id": "00Q1"})
    envelope = envelope_from_connector_response(response)
    assert envelope["error"] is None
    assert envelope["command_response"]["http_status"] == 200
    assert envelope["command_response"]["body"]["record_id"] == "00Q1"
    assert envelope["command_response_version"] == 2


@pytest.mark.parametrize(
    ("category", "expected_status"),
    [("RETRYABLE", 503), ("BUSINESS", 400), ("AUTH", 401), ("FATAL", 500), (None, 500)],
)
def test_envelope_maps_error_category_onto_http_status(category: Any, expected_status: int) -> None:
    response = MagicMock(
        success=False,
        error_code="SOME_ERROR",
        error_category=category,
        message="boom",
    )
    envelope = envelope_from_connector_response(response)
    assert envelope["command_response"]["http_status"] == expected_status
    assert envelope["error"]["error_code"] == "SOME_ERROR"


def test_envelope_appends_validation_details_to_the_message() -> None:
    """node-wire reports every validation failure with the same generic
    message and names the offending field only in details."""
    response = MagicMock(
        success=False,
        error_code="VALIDATION_ERROR",
        error_category="BUSINESS",
        message="Input validation failed; please check the request payload.",
        details=[
            {
                "loc": ("create_subscription", "customer_id"),
                "msg": "Value error, customer_id must start with 'cus_'",
                "type": "value_error",
            }
        ],
    )
    envelope = envelope_from_connector_response(response)
    message = envelope["error"]["message"]
    assert "create_subscription.customer_id" in message
    assert "must start with 'cus_'" in message
    assert envelope["command_response"]["http_status"] == 400


def test_envelope_leaves_the_message_alone_without_usable_details() -> None:
    response = MagicMock(
        success=False,
        error_code="SOME_ERROR",
        error_category="FATAL",
        message="boom",
        details=None,
    )
    assert envelope_from_connector_response(response)["error"]["message"] == "boom"


async def test_a_failure_reported_as_data_stays_a_success_envelope() -> None:
    """m8flow_n8n nests an n8n-side error in data; a top-level error would
    suspend the process instance and hang the UI."""
    response = MagicMock(
        success=True,
        data={"status_code": 500, "error_code": "N8nRequestFailed", "message": "boom"},
    )
    envelope = envelope_from_connector_response(response)
    assert envelope["error"] is None
    assert envelope["command_response"]["body"]["error_code"] == "N8nRequestFailed"


async def test_execute_rejects_an_unknown_command() -> None:
    envelope = await execute_m8flow("github", "NoSuchCommand", {})
    assert envelope["error"]["error_code"] == "UnknownCommand"


async def test_execute_reports_a_missing_wheel_rather_than_raising() -> None:
    with patch(
        "m8flow_node_wire_proxy.node_wire_gateway.get_m8flow_connector",
        side_effect=ImportError("No module named 'node_wire_m8flow_github'"),
    ):
        envelope = await execute_m8flow("github", "ConnectRepository", {"token": "t", "owner": "o", "repo": "r"})
    assert envelope["error"]["error_code"] == "ConnectorUnavailable"


async def test_execute_runs_the_connector_and_envelopes_its_response() -> None:
    connector = MagicMock()
    connector.return_value.run = AsyncMock(
        return_value=MagicMock(success=True, data={"status_code": 200, "body": {"ok": True}})
    )
    with patch(
        "m8flow_node_wire_proxy.node_wire_gateway.get_m8flow_connector",
        return_value=connector,
    ):
        envelope = await execute_m8flow(
            "github", "ConnectRepository", {"token": "t", "owner": "o", "repo": "r", "spiff__x": 1}
        )

    connector.return_value.run.assert_awaited_once()
    sent = connector.return_value.run.await_args.args[0]
    assert sent == {"action": "connect_repository", "token": "t", "owner": "o", "repo": "r"}
    assert envelope["error"] is None
    assert envelope["command_response"]["body"]["body"] == {"ok": True}


def test_do_route_dispatches_m8flow_connectors(client: TestClient) -> None:
    """The route must pick execute_m8flow, not execute_http_v2 (which 'http'-gates)."""
    connector = MagicMock()
    connector.return_value.run = AsyncMock(return_value=MagicMock(success=True, data={"sent": True}))
    with patch(
        "m8flow_node_wire_proxy.node_wire_gateway.get_m8flow_connector",
        return_value=connector,
    ):
        response = client.post(
            "/v1/do/slack/PostMessage",
            json={"token": "t", "channel": "#general", "message": "hi"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["command_response"]["body"] == {"sent": True}
