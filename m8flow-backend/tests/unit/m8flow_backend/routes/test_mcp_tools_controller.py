"""Unit tests for the MCP tools controller.

Covers the three thin Connexion operation functions over
services.mcp_catalog_service -- catalog listing, connection ping, and tool
execution -- including the bearer-token forwarding and the error/status-code
mapping contract each documents. Mirrors test_connectors_controller.py's
Flask-app-context + patch pattern; services.mcp_catalog_service's functions are
async, so they are patched with AsyncMock and driven through the controller's
own _run_coroutine bridge exactly as a real request would.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from flask import Flask

from m8flow_backend.routes import mcp_tools_controller


def _request_context(headers=None):
    app = Flask(__name__)
    return app.test_request_context("/m8flow/mcp-tools", headers=headers or {})


def test_list_mcp_tools_catalog_returns_catalog_on_success():
    catalog = {
        "server_url": "https://mcp.example",
        "protocol_version": "2024-11-05",
        "tool_count": 1,
        "tools": [{"name": "ping_tool", "badge": "read"}],
    }
    with _request_context({"Authorization": "Bearer abc123"}), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "get_catalog",
        AsyncMock(return_value=catalog),
    ) as mock_get_catalog:
        response = mcp_tools_controller.list_mcp_tools_catalog()

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == catalog
    mock_get_catalog.assert_awaited_once_with("Bearer abc123")


def test_list_mcp_tools_catalog_maps_error_dict_to_502():
    with _request_context(), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "get_catalog",
        AsyncMock(return_value={"error": "Could not connect to the MCP server: boom"}),
    ):
        response = mcp_tools_controller.list_mcp_tools_catalog()

    assert response.status_code == 502
    body = json.loads(response.get_data(as_text=True))
    assert body["error_code"] == "mcp_catalog_unavailable"
    assert "boom" in body["message"]


def test_list_mcp_tools_catalog_forwards_empty_token_when_header_missing():
    """No Authorization header -> "" forwarded, never None (service does
    `token.strip() if isinstance(token, str) else ""`, so a raw string is the
    contract even when the header is absent)."""
    with _request_context(), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "get_catalog",
        AsyncMock(return_value={"tools": [], "tool_count": 0}),
    ) as mock_get_catalog:
        mcp_tools_controller.list_mcp_tools_catalog()

    mock_get_catalog.assert_awaited_once_with("")


def test_check_mcp_connection_always_returns_200_regardless_of_ok_or_authorized():
    ping_result = {"ok": False, "latency_ms": 12, "protocol_version": None, "authorized": False}
    with _request_context({"Authorization": "Bearer xyz"}), patch.object(
        mcp_tools_controller.mcp_catalog_service, "ping", AsyncMock(return_value=ping_result)
    ) as mock_ping:
        response = mcp_tools_controller.check_mcp_connection()

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == ping_result
    mock_ping.assert_awaited_once_with("Bearer xyz")


def test_execute_mcp_tool_passes_body_fields_through_and_returns_result():
    with _request_context({"Authorization": "Bearer abc123"}), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "execute_tool",
        AsyncMock(return_value={"result": "done"}),
    ) as mock_execute:
        response = mcp_tools_controller.execute_mcp_tool(
            {"tool_name": "some_tool", "arguments": {"x": 1}, "confirm": True}
        )

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {"result": "done"}
    mock_execute.assert_awaited_once_with("Bearer abc123", "some_tool", {"x": 1}, True)


def test_execute_mcp_tool_defaults_arguments_to_empty_dict_and_confirm_to_false():
    with _request_context({"Authorization": "Bearer abc123"}), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "execute_tool",
        AsyncMock(return_value={"result": "ok"}),
    ) as mock_execute:
        mcp_tools_controller.execute_mcp_tool({"tool_name": "some_tool"})

    mock_execute.assert_awaited_once_with("Bearer abc123", "some_tool", {}, False)


def test_execute_mcp_tool_maps_service_status_code_400_through():
    with _request_context(), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "execute_tool",
        AsyncMock(
            return_value={
                "error": "confirmation_required",
                "message": "This tool performs a write operation and requires confirm=true to execute.",
                "status_code": 400,
            }
        ),
    ):
        response = mcp_tools_controller.execute_mcp_tool({"tool_name": "writer_tool"})

    assert response.status_code == 400
    body = json.loads(response.get_data(as_text=True))
    assert body["error_code"] == "confirmation_required"


def test_execute_mcp_tool_maps_upstream_auth_rejection_through_as_502():
    """An auth rejection by the MCP server reaches this controller as a 502.

    The service normalizes the upstream 401/403 itself (see
    ``mcp_catalog_service.execute_tool``) precisely so this endpoint never answers
    a POST with 401 -- the frontend's HttpService would read that as an expired
    session and redirect the admin to login. The controller just passes the
    service's status through; the reason survives in the message.
    """
    with _request_context(), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "execute_tool",
        AsyncMock(
            return_value={
                "error": "mcp_call_failed",
                "message": "Not authorized to reach the MCP server (HTTP 403).",
                "status_code": 502,
            }
        ),
    ):
        response = mcp_tools_controller.execute_mcp_tool({"tool_name": "dangerous_tool"})

    assert response.status_code == 502
    body = json.loads(response.get_data(as_text=True))
    assert body["error_code"] == "mcp_call_failed"
    assert "HTTP 403" in body["message"]


def test_execute_mcp_tool_defaults_to_400_when_service_omits_status_code():
    with _request_context(), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "execute_tool",
        AsyncMock(return_value={"error": "unexpected_shape", "message": "no status_code key"}),
    ):
        response = mcp_tools_controller.execute_mcp_tool({"tool_name": "some_tool"})

    assert response.status_code == 400


def test_execute_mcp_tool_returns_400_not_500_when_body_is_none():
    """Regression guard: api.yml's requestBody schema is enforced by Connexion's
    request pipeline, not by this function -- a malformed/empty JSON body can
    still reach here as None. Dereferencing `.get` on it must not 500."""
    with _request_context(), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "execute_tool",
        AsyncMock(side_effect=AssertionError("the service must never be called for an invalid body")),
    ) as mock_execute:
        response = mcp_tools_controller.execute_mcp_tool(None)

    assert response.status_code == 400
    body = json.loads(response.get_data(as_text=True))
    assert body["error_code"] == "invalid_request_body"
    mock_execute.assert_not_awaited()


def test_execute_mcp_tool_returns_400_not_500_when_body_is_not_a_dict():
    with _request_context(), patch.object(
        mcp_tools_controller.mcp_catalog_service,
        "execute_tool",
        AsyncMock(side_effect=AssertionError("the service must never be called for an invalid body")),
    ) as mock_execute:
        response = mcp_tools_controller.execute_mcp_tool("not-a-dict")

    assert response.status_code == 400
    body = json.loads(response.get_data(as_text=True))
    assert body["error_code"] == "invalid_request_body"
    mock_execute.assert_not_awaited()
