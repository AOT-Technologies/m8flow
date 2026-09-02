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
from mcp import McpError
from mcp.types import ErrorData

from m8flow_backend.services import mcp_catalog_service


def test_mcp_package_is_importable():
    """Regression guard for the runtime-only dependency install step (mcp is
    installed at runtime, not pinned in any pyproject.toml -- see
    bin/run_m8flow_backend.sh)."""
    import mcp  # noqa: F401 -- presence is the assertion


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


def _install_connection_counting_fake_client(monkeypatch, session):
    """Install the fake client and return the list it appends one entry per connection to.

    Same wiring as ``_install_fake_client``, except the ``streamablehttp_client``
    stand-in records every call. The returned list's length is therefore the exact
    number of MCP client connections a service function opened.
    """
    connections = []

    def factory(server_url, headers=None):
        connections.append({"server_url": server_url, "headers": headers})
        return _FakeStreamContext()

    monkeypatch.setattr(mcp_catalog_service, "mcp_server_url", lambda: "https://mcp.example")
    monkeypatch.setattr(mcp_catalog_service, "streamablehttp_client", factory)
    monkeypatch.setattr(mcp_catalog_service, "ClientSession", _fake_client_session(session))
    return connections


class _SwallowingSessionContext:
    """A ``ClientSession`` stand-in whose ``__aexit__`` absorbs the exception.

    Models the one narrow real-world case where a body exception never reaches
    ``execute_tool``'s ``except``: an anyio task group ``__aexit__`` returns True
    when it swallows a cancellation belonging to its own cancel scope, so control
    resumes after the ``async with`` with no result recorded.
    """

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return True


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """An ``httpx.HTTPStatusError`` carrying a real response with ``status_code``."""
    request = httpx.Request("POST", "https://mcp.example")
    return httpx.HTTPStatusError(
        f"{status_code} error",
        request=request,
        response=httpx.Response(status_code, request=request),
    )


_NO_DESCRIPTION_OVERRIDE = object()


def _make_tool(
    name: str,
    *,
    read_only: bool,
    tags: list[str] | None = None,
    properties=None,
    required=None,
    description: object = _NO_DESCRIPTION_OVERRIDE,
):
    return SimpleNamespace(
        name=name,
        description=f"{name} description" if description is _NO_DESCRIPTION_OVERRIDE else description,
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

    assert result == {"error": "Could not connect to the MCP server."}


def test_get_catalog_error_message_never_leaks_raw_exception_text(monkeypatch):
    """Raw exception text (can carry internal hostnames/ports) must never
    reach the API response."""
    _install_fake_client(
        monkeypatch,
        session=None,
        raise_exc=httpx.ConnectError(
            "[Errno 61] Connection refused: internal-mcp.svc.cluster.local:9000"
        ),
    )

    result = asyncio.run(mcp_catalog_service.get_catalog("token-abc"))

    assert result == {"error": "Could not connect to the MCP server."}
    assert "internal-mcp.svc.cluster.local" not in result["error"]
    assert "9000" not in result["error"]


def test_get_catalog_error_message_never_leaks_mcp_error_details(monkeypatch):
    """Same sanitization for a protocol-level McpError from the server itself."""
    mcp_error = McpError(ErrorData(code=-32000, message="internal trace: token=super-secret-value"))
    _install_fake_client(monkeypatch, session=None, raise_exc=mcp_error)

    result = asyncio.run(mcp_catalog_service.get_catalog("token-abc"))

    assert result == {"error": "MCP server rejected the request."}
    assert "super-secret-value" not in result["error"]


def test_get_catalog_returns_error_dict_when_server_url_not_configured(monkeypatch):
    """503, not 502: this path never attempts an outbound call."""
    monkeypatch.setattr(mcp_catalog_service, "mcp_server_url", lambda: "")

    result = asyncio.run(mcp_catalog_service.get_catalog("token-abc"))

    assert result == {
        "error": "M8FLOW_MCP_SERVER_URL is not configured.",
        "status_code": 503,
    }


def test_get_catalog_tolerates_a_tool_whose_input_schema_is_malformed(monkeypatch):
    """A malformed upstream inputSchema.properties/required (not a dict/list)
    must degrade that tool's parameters to [] rather than crash the catalog."""
    well_formed_tool = _make_tool(
        "list_reports", read_only=True, properties={"limit": {"type": "integer"}}, required=["limit"]
    )
    malformed_tool = _make_tool("weird_tool", read_only=True, properties="not-a-dict", required=123)

    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=[well_formed_tool, malformed_tool])),
    )
    _install_fake_client(monkeypatch, session)

    result = asyncio.run(mcp_catalog_service.get_catalog("token-abc"))

    tools_by_name = {tool["name"]: tool for tool in result["tools"]}
    assert tools_by_name["list_reports"]["parameters"] == [
        {"name": "limit", "type": "integer", "required": True, "description": ""}
    ]
    assert tools_by_name["weird_tool"]["parameters"] == []


def test_get_catalog_coerces_a_non_string_tool_description_to_empty_string(monkeypatch):
    """A non-string tool.description (dict/int/None) must coerce to "" rather
    than reach the API response."""
    dict_description_tool = _make_tool("weird_tool", read_only=True, description={"nested": "dict"})
    int_description_tool = _make_tool("other_weird_tool", read_only=True, description=404)
    none_description_tool = _make_tool("no_description_tool", read_only=True, description=None)

    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
        list_tools=AsyncMock(
            return_value=SimpleNamespace(
                tools=[dict_description_tool, int_description_tool, none_description_tool]
            )
        ),
    )
    _install_fake_client(monkeypatch, session)

    result = asyncio.run(mcp_catalog_service.get_catalog("token-abc"))

    descriptions_by_name = {tool["name"]: tool["description"] for tool in result["tools"]}
    assert descriptions_by_name == {
        "weird_tool": "",
        "other_weird_tool": "",
        "no_description_tool": "",
    }


def test_get_catalog_forwards_a_well_formed_bearer_header_for_an_empty_or_whitespace_token(monkeypatch):
    """An empty/blank token still produces a well-formed Bearer header, never
    a missing Authorization header."""
    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=[])),
    )
    connections = _install_connection_counting_fake_client(monkeypatch, session)

    asyncio.run(mcp_catalog_service.get_catalog(""))
    asyncio.run(mcp_catalog_service.get_catalog("   "))

    assert [connection["headers"] for connection in connections] == [
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer "},
    ]


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


def test_ping_failure_response_never_carries_raw_exception_text(monkeypatch):
    """ping()'s response shape has no field for an error message at all --
    lock that in so it can't be reintroduced from raw exception text."""
    _install_fake_client(
        monkeypatch,
        session=None,
        raise_exc=httpx.ConnectError("internal-mcp.svc.cluster.local:9000 refused"),
    )

    result = asyncio.run(mcp_catalog_service.ping("token-abc"))

    assert set(result.keys()) == {"ok", "latency_ms", "protocol_version", "authorized"}
    assert "internal-mcp" not in str(result)


# ---------------------------------------------------------------------------
# execute_tool
# ---------------------------------------------------------------------------


def test_execute_tool_returns_503_when_server_url_not_configured(monkeypatch):
    """Same 503-vs-502 distinction as get_catalog's."""
    monkeypatch.setattr(mcp_catalog_service, "mcp_server_url", lambda: "")

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "list_reports", {}, False))

    assert result == {
        "error": "catalog_unavailable",
        "message": "M8FLOW_MCP_SERVER_URL is not configured.",
        "status_code": 503,
    }


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


def test_execute_tool_returns_404_when_the_tool_name_is_not_in_the_catalog(monkeypatch):
    """The unknown-tool gate now runs inside the single session, against the tools
    just listed there -- not against a separately fetched catalog. It must still be
    a 404, and must still stop before ``tools/call`` is issued.
    """
    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
        list_tools=AsyncMock(
            return_value=SimpleNamespace(tools=[_make_tool("list_reports", read_only=True)])
        ),
        call_tool=AsyncMock(side_effect=AssertionError("call_tool must not run for an unknown tool")),
    )
    _install_fake_client(monkeypatch, session)

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "no_such_tool", {}, True))

    assert result == {
        "error": "tool_not_found",
        "message": "No MCP tool named 'no_such_tool' was found in the catalog.",
        "status_code": 404,
    }
    session.call_tool.assert_not_awaited()


def test_execute_tool_reports_an_upstream_401_as_502_not_401(monkeypatch):
    """Regression guard: an MCP-server auth rejection must never become this
    endpoint's own 401.

    The caller's token already passed m8flow-backend's own authn/RBAC to reach
    here; only the separately-deployed MCP server refused it. A 401 on this POST
    would make the frontend's HttpService treat the session as expired and bounce
    the admin to the login page, so the status is normalized to 502 (matching what
    get_catalog returns for the identical failure) while the reason stays in the
    message.
    """
    _install_fake_client(monkeypatch, session=None, raise_exc=_http_status_error(401))

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "list_reports", {}, True))

    assert result["status_code"] == 502
    assert result["error"] == "mcp_call_failed"
    assert result["message"] == "Not authorized to reach the MCP server (HTTP 401)."


def test_execute_tool_reports_a_taskgroup_wrapped_upstream_403_as_502(monkeypatch):
    """Same normalization for a 403, and through the ExceptionGroup wrapper the
    real transport always adds (streamablehttp_client/ClientSession run their I/O
    inside anyio task groups)."""
    wrapped = BaseExceptionGroup(
        "unhandled errors in a TaskGroup", [_http_status_error(403)]
    )
    _install_fake_client(monkeypatch, session=None, raise_exc=wrapped)

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "list_reports", {}, True))

    assert result["status_code"] == 502
    assert result["message"] == "Not authorized to reach the MCP server (HTTP 403)."


def test_execute_tool_still_forwards_a_non_auth_upstream_status(monkeypatch):
    """Only auth rejections are rewritten; other upstream statuses pass through."""
    _install_fake_client(monkeypatch, session=None, raise_exc=_http_status_error(429))

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "list_reports", {}, True))

    assert result["status_code"] == 429
    assert result["message"] == "MCP server returned HTTP 429."


def test_execute_tool_error_message_never_leaks_raw_exception_text(monkeypatch):
    """Same sanitization as get_catalog's, for the non-HTTP failure branch."""
    _install_fake_client(
        monkeypatch,
        session=None,
        raise_exc=httpx.ConnectError("internal-mcp.svc.cluster.local:9000 refused"),
    )

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "list_reports", {}, True))

    assert result["status_code"] == 502
    assert result["message"] == "Could not connect to the MCP server."
    assert "internal-mcp" not in result["message"]


def test_execute_tool_returns_an_error_dict_when_the_session_swallows_the_call_failure(monkeypatch):
    """No AttributeError may escape when the session closes without a result.

    ``execute_tool`` promises to return an error dict rather than raise. If the
    session's own ``__aexit__`` absorbs the exception raised by ``call_tool()``,
    the code after the ``async with`` sees no result and no ``early`` outcome --
    dereferencing ``call_result.isError`` there would 500 the endpoint with a
    stack trace.
    """
    read_tool = _make_tool("list_reports", read_only=True, tags=["reporting"])
    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=[read_tool])),
        call_tool=AsyncMock(side_effect=RuntimeError("transport died mid-call")),
    )
    monkeypatch.setattr(mcp_catalog_service, "mcp_server_url", lambda: "https://mcp.example")
    monkeypatch.setattr(
        mcp_catalog_service, "streamablehttp_client", _fake_streamablehttp_client(None)
    )
    monkeypatch.setattr(
        mcp_catalog_service,
        "ClientSession",
        lambda read_stream, write_stream: _SwallowingSessionContext(session),
    )

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "list_reports", {}, True))

    assert result == {
        "error": "mcp_call_failed",
        "message": "The MCP session closed before 'list_reports' returned a result.",
        "status_code": 502,
    }


def test_execute_tool_opens_exactly_one_connection_and_initializes_once(monkeypatch):
    """Regression guard for the single-session refactor.

    execute_tool used to call get_catalog() first (one connection + initialize) and
    then open a second session to make the actual call. Resolving the tool from the
    same session's own list_tools() halves that cost, so this pins the counts: one
    connection, one initialize, one list_tools, one call_tool.
    """
    read_tool = _make_tool("list_reports", read_only=True, tags=["reporting"])
    call_result = SimpleNamespace(isError=False, structuredContent={"rows": []}, content=None)

    session = SimpleNamespace(
        initialize=AsyncMock(return_value=SimpleNamespace(protocolVersion="2024-11-05")),
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=[read_tool])),
        call_tool=AsyncMock(return_value=call_result),
    )
    connections = _install_connection_counting_fake_client(monkeypatch, session)

    result = asyncio.run(mcp_catalog_service.execute_tool("token-abc", "list_reports", {}, False))

    assert result == {"result": {"rows": []}}
    assert len(connections) == 1, f"expected exactly one MCP connection, opened {len(connections)}"
    assert connections[0]["headers"] == {"Authorization": "Bearer token-abc"}
    assert session.initialize.await_count == 1
    assert session.list_tools.await_count == 1
    assert session.call_tool.await_count == 1


def test_param_type_unwraps_an_optional_annotation_to_its_real_type():
    """`x: int | None` compiles to anyOf with no top-level "type".

    Reading "type" alone reported "any"; the catalog page has no coercion branch for
    "any", so it fell through to its string branch and sent an integer parameter as
    "123", which the tool's own schema validation then rejected.
    """
    assert mcp_catalog_service._param_type({"anyOf": [{"type": "integer"}, {"type": "null"}]}) == "integer"
    assert mcp_catalog_service._param_type({"anyOf": [{"type": "string"}, {"type": "null"}]}) == "string"
    # Order must not matter -- pydantic is free to emit the null variant first.
    assert mcp_catalog_service._param_type({"anyOf": [{"type": "null"}, {"type": "boolean"}]}) == "boolean"


def test_param_type_passes_through_a_plain_declared_type():
    assert mcp_catalog_service._param_type({"type": "string"}) == "string"


def test_param_type_handles_a_list_valued_type():
    """JSON Schema allows `"type": ["integer", "null"]` for the same shape."""
    assert mcp_catalog_service._param_type({"type": ["integer", "null"]}) == "integer"


def test_param_type_falls_back_to_any_when_no_usable_type_is_present():
    """Must degrade, not raise -- _tool_parameters runs outside get_catalog's try/except."""
    for schema in ({}, {"anyOf": []}, {"anyOf": [{"no": "type"}]}, {"anyOf": ["not-a-dict"]}, {"type": ["null"]}):
        assert mcp_catalog_service._param_type(schema) == "any"


def test_tool_parameters_reports_the_unwrapped_type_for_an_optional_param():
    """End-to-end through the catalog's parameter derivation, not just the helper."""
    tool = SimpleNamespace(
        inputSchema={
            "properties": {
                "process_instance_id": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}],
                    "description": "Filter by workflow instance",
                }
            },
            "required": [],
        }
    )
    (param,) = mcp_catalog_service._tool_parameters(tool)
    assert param == {
        "name": "process_instance_id",
        "type": "integer",
        "required": False,
        "description": "Filter by workflow instance",
    }
