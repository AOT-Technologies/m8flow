"""Unit tests for mcp_catalog_service.

Covers get_catalog, ping, and execute_tool -- the MCP-client bridge to the
m8flow-mcp server. The MCP SDK client (streamablehttp_client / ClientSession)
is fully mocked here so no test ever opens a real network connection; async
functions are driven with plain ``asyncio.run(...)`` from sync test bodies,
mirroring how the controller's own ``_run_coroutine`` bridges sync Flask
views to this module's async functions (see test_mcp_tools_controller.py,
which drives the same functions via AsyncMock through that bridge instead).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from m8flow_backend.services import mcp_catalog_service


class _FakeStreamContext:
    """Fakes the async context manager returned by ``streamablehttp_client(...)``."""

    def __init__(self, read_stream: str = "read-stream", write_stream: str = "write-stream"):
        self._read_stream = read_stream
        self._write_stream = write_stream

    async def __aenter__(self):
        return (self._read_stream, self._write_stream, lambda: "session-id")

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSessionContext:
    """Fakes the async context manager returned by ``ClientSession(...)``."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _fake_streamablehttp_client(raise_exc: BaseException | None = None):
    """Build a fake replacement for ``mcp_catalog_service.streamablehttp_client``.

    When ``raise_exc`` is given, calling the fake raises it synchronously --
    which happens while still inside get_catalog/ping/execute_tool's
    surrounding ``try: async with ... except Exception:`` block, exactly like
    a real connection failure would.
    """

    def factory(server_url, headers=None):
        if raise_exc is not None:
            raise raise_exc
        return _FakeStreamContext()

    return factory


def _fake_client_session(session):
    """Build a fake replacement for ``mcp_catalog_service.ClientSession`` bound to ``session``."""

    def factory(read_stream, write_stream):
        return _FakeSessionContext(session)

    return factory


def _install_fake_client(monkeypatch, session, *, raise_exc: BaseException | None = None):
    monkeypatch.setattr(mcp_catalog_service, "mcp_server_url", lambda: "https://mcp.example")
    monkeypatch.setattr(
        mcp_catalog_service, "streamablehttp_client", _fake_streamablehttp_client(raise_exc)
    )
    if session is not None:
        monkeypatch.setattr(mcp_catalog_service, "ClientSession", _fake_client_session(session))


def _make_tool(name: str, *, read_only: bool, tags: list[str] | None = None, properties=None, required=None):
    return SimpleNamespace(
        name=name,
        description=f"{name} description",
        meta={"fastmcp": {"tags": tags or []}},
        annotations=SimpleNamespace(readOnlyHint=read_only),
        inputSchema={"properties": properties or {}, "required": required or []},
    )


# ---------------------------------------------------------------------------
# get_catalog
# ---------------------------------------------------------------------------


def test_get_catalog_happy_path_derives_category_and_badge_from_tags_and_annotations(monkeypatch):
    read_tool = _make_tool(
        "list_reports",
        read_only=True,
        tags=["reporting"],
        properties={"limit": {"type": "integer", "description": "max rows"}},
        required=[],
    )
    write_tool = _make_tool("delete_report", read_only=False, tags=["reporting"])
    untagged_tool = _make_tool("noop", read_only=True, tags=[])

    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=[read_tool, write_tool, untagged_tool])),
    )
    _install_fake_client(monkeypatch, session)

    result = asyncio.run(mcp_catalog_service.get_catalog("token-abc"))

    assert result["server_url"] == "https://mcp.example"
    assert result["protocol_version"] == "2024-11-05"
    assert result["tool_count"] == 3

    tools_by_name = {tool["name"]: tool for tool in result["tools"]}
    assert tools_by_name["list_reports"]["category"] == "reporting"
    assert tools_by_name["list_reports"]["badge"] == "read"
    assert tools_by_name["list_reports"]["parameters"] == [
        {"name": "limit", "type": "integer", "required": False, "description": "max rows"}
    ]
    assert tools_by_name["delete_report"]["category"] == "reporting"
    assert tools_by_name["delete_report"]["badge"] == "write"
    assert tools_by_name["noop"]["category"] == "uncategorized"
    assert tools_by_name["noop"]["badge"] == "read"


def test_get_catalog_returns_error_dict_instead_of_raising_on_connection_failure(monkeypatch):
    _install_fake_client(monkeypatch, session=None, raise_exc=httpx.ConnectError("boom"))

    result = asyncio.run(mcp_catalog_service.get_catalog("token-abc"))

    assert list(result.keys()) == ["error"]
    assert "boom" in result["error"]


def test_get_catalog_returns_error_dict_when_server_url_not_configured(monkeypatch):
    monkeypatch.setattr(mcp_catalog_service, "mcp_server_url", lambda: "")

    result = asyncio.run(mcp_catalog_service.get_catalog("token-abc"))

    assert result == {"error": "M8FLOW_MCP_SERVER_URL is not configured."}


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------


def test_ping_success(monkeypatch):
    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
    )
    _install_fake_client(monkeypatch, session)

    result = asyncio.run(mcp_catalog_service.ping("token-abc"))

    assert result["ok"] is True
    assert result["protocol_version"] == "2024-11-05"
    assert result["authorized"] is True
    assert result["latency_ms"] >= 0


def test_ping_failure_returns_not_ok_without_raising(monkeypatch):
    _install_fake_client(monkeypatch, session=None, raise_exc=httpx.ConnectError("unreachable"))

    result = asyncio.run(mcp_catalog_service.ping("token-abc"))

    assert result["ok"] is False
    assert result["protocol_version"] is None
    # A plain connection failure never disproves authorization.
    assert result["authorized"] is True


# ---------------------------------------------------------------------------
# execute_tool
# ---------------------------------------------------------------------------


def test_execute_tool_happy_path_for_a_read_tool(monkeypatch):
    read_tool = _make_tool("list_reports", read_only=True, tags=["reporting"])
    call_result = SimpleNamespace(isError=False, structuredContent={"rows": []}, content=None)

    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=[read_tool])),
        call_tool=AsyncMock(return_value=call_result),
    )
    _install_fake_client(monkeypatch, session)

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "list_reports", {}, False))

    assert result == {"result": {"rows": []}}
    session.call_tool.assert_awaited_once_with("list_reports", {})


def test_execute_tool_blocks_write_tool_without_confirm(monkeypatch):
    write_tool = _make_tool("delete_report", read_only=False, tags=["reporting"])

    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=[write_tool])),
        call_tool=AsyncMock(side_effect=AssertionError("call_tool must not run without confirm=True")),
    )
    _install_fake_client(monkeypatch, session)

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "delete_report", {}, False))

    assert result == {
        "error": "confirmation_required",
        "message": "This tool performs a write operation and requires confirm=true to execute.",
        "status_code": 400,
    }
    session.call_tool.assert_not_awaited()


def test_execute_tool_blocks_a_tool_added_to_sensitive_tool_names(monkeypatch):
    """Proves the SENSITIVE_TOOL_NAMES seam works, without shipping a real sensitive tool.

    SENSITIVE_TOOL_NAMES ships empty (see the module docstring for why); this
    monkeypatches it locally to prove execute_tool's enforcement point reads
    it and short-circuits -- before ever attempting an MCP connection.
    """
    monkeypatch.setattr(mcp_catalog_service, "SENSITIVE_TOOL_NAMES", frozenset({"delete_everything"}))

    def _fail_if_a_connection_is_attempted(*_args, **_kwargs):
        raise AssertionError("a sensitive tool must be blocked before any MCP connection is attempted")

    monkeypatch.setattr(mcp_catalog_service, "streamablehttp_client", _fail_if_a_connection_is_attempted)

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "delete_everything", {}, True))

    assert result == {
        "error": "sensitive_tool_disabled",
        "message": "Disabled for MCP clients in this tenant. Enable it under Manage permissions.",
        "status_code": 403,
    }
