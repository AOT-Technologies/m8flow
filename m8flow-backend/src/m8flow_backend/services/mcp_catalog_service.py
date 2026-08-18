"""MCP catalog service: MCP-client bridge to the m8flow-mcp server for the admin catalog UI.

Every function here opens its own short-lived MCP client session against the
independently-deployed m8flow-mcp server (``m8flow_backend.config.mcp_server_url``),
forwarding the CALLING USER'S OWN bearer token as the ``Authorization`` header. This
is deliberate: it makes the catalog (and any tool call made through it) see exactly
what a real MCP client acting on that user's behalf would see, so tenant scoping
matches the caller's own permissions. Every function therefore takes ``token`` as an
explicit argument -- nothing here reads a token from Flask ``g`` or any other global
request state.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from mcp import McpError
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

from m8flow_backend.config import mcp_server_url

logger = logging.getLogger(__name__)

_AUTH_ERROR_STATUS_CODES = frozenset({401, 403})


def _auth_headers(token: str) -> dict[str, str]:
    """Build the Authorization header carrying the caller's own bearer token.

    Accepts either a raw token or one already prefixed with "Bearer " so this
    stays correct regardless of how the eventual controller extracts it from the
    incoming request (this codebase's existing bearer-token readers, e.g.
    ``authentication_service_patch.py``, strip the scheme themselves before using
    the value, so a raw token is the expected case).
    """
    raw_token = token.strip() if isinstance(token, str) else ""
    if raw_token.lower().startswith("bearer "):
        raw_token = raw_token[len("bearer "):].strip()
    return {"Authorization": f"Bearer {raw_token}"}


def _tool_tags(tool: Any) -> list[str]:
    """Return one tool's FastMCP tags from its wire ``_meta`` payload.

    FastMCP tags are not part of the MCP `Tool` schema itself; FastMCP nests them
    at ``_meta.fastmcp.tags`` (older servers used ``_meta._fastmcp.tags``). Reading
    both namespaces here depends only on that wire shape, not on importing the
    `fastmcp` package (m8flow-backend only needs the `mcp` client SDK).
    """
    meta = getattr(tool, "meta", None) or {}
    for namespace_key in ("fastmcp", "_fastmcp"):
        namespace = meta.get(namespace_key)
        if isinstance(namespace, dict):
            tags = namespace.get("tags")
            if isinstance(tags, list) and tags:
                return [str(tag) for tag in tags]
    return []


def _tool_badge(tool: Any) -> str:
    """"read" when the tool's annotations mark it read-only, else "write".

    Read-only means the tool's ``annotations.readOnlyHint`` is exactly ``True``; a
    missing or absent hint is treated as "write", the safe default. The catalog UI
    reads this badge to decide whether "Try it" needs a confirmation step, and
    ``execute_tool()`` enforces that same distinction server-side.
    """
    annotations = getattr(tool, "annotations", None)
    read_only_hint = getattr(annotations, "readOnlyHint", None) if annotations is not None else None
    return "read" if read_only_hint is True else "write"


def _tool_parameters(tool: Any) -> list[dict[str, Any]]:
    """Derive the catalog's parameter list from a tool's JSON-Schema inputSchema.

    ``properties``/``required`` are never schema-validated by the mcp SDK
    itself, so a malformed upstream tool must degrade to an empty parameter
    list here rather than raise -- this runs outside get_catalog's try/except.
    """
    schema = getattr(tool, "inputSchema", None) or {}
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}
    required = schema.get("required") or []
    required_names = set(required) if isinstance(required, list) else set()

    parameters: list[dict[str, Any]] = []
    for param_name, param_schema in properties.items():
        if not isinstance(param_schema, dict):
            param_schema = {}
        parameters.append(
            {
                "name": param_name,
                "type": param_schema.get("type", "any"),
                "required": param_name in required_names,
                "description": param_schema.get("description", ""),
            }
        )
    return parameters


def _tool_description(tool: Any) -> str:
    """A tool's description, guaranteed to be a string.

    The mcp SDK types this ``str | None``, but this codebase pins a wide
    ``mcp>=1.9.0,<2.0.0`` range -- guard it explicitly too, same as
    ``_tool_parameters``, so a non-string value degrades to ``""`` instead of
    reaching the API response.
    """
    description = getattr(tool, "description", None)
    return description if isinstance(description, str) else ""


def _tool_summary(tool: Any) -> dict[str, Any]:
    """Catalog entry for one MCP tool: display metadata plus derived parameters."""
    tags = _tool_tags(tool)
    return {
        "name": tool.name,
        "description": _tool_description(tool),
        "category": tags[0] if tags else "uncategorized",
        "badge": _tool_badge(tool),
        "parameters": _tool_parameters(tool),
    }


def _content_blocks_to_json(content: list[Any] | None) -> list[dict[str, Any]]:
    """Serialize MCP content blocks (TextContent, ImageContent, ...) to plain dicts."""
    blocks: list[dict[str, Any]] = []
    for block in content or []:
        dump = getattr(block, "model_dump", None)
        blocks.append(dump(mode="json", exclude_none=True) if callable(dump) else block)
    return blocks


def _unwrap_exception_group(exc: BaseException) -> BaseException:
    """Unwrap anyio/asyncio TaskGroup ``ExceptionGroup`` wrappers down to the leaf cause.

    ``streamablehttp_client``/``ClientSession`` run their transport I/O inside
    internal task groups, so a plain ``httpx.HTTPStatusError`` (e.g. a 401 from the
    MCP server) or ``httpx.ConnectError`` never reaches callers directly -- it comes
    wrapped as ``ExceptionGroup("unhandled errors in a TaskGroup", [the real exc])``.
    Every classification below (auth vs. other failure) needs the real exception,
    not that wrapper, so this always runs first.
    """
    seen: set[int] = set()
    current = exc
    while isinstance(current, BaseExceptionGroup) and current.exceptions and id(current) not in seen:
        seen.add(id(current))
        current = current.exceptions[0]
    return current


def _http_status_from_exception(exc: BaseException) -> int | None:
    """The HTTP status code of an (unwrapped) exception, if it is an HTTPStatusError."""
    leaf = _unwrap_exception_group(exc)
    if isinstance(leaf, httpx.HTTPStatusError) and leaf.response is not None:
        return leaf.response.status_code
    return None


def _connection_error_message(exc: BaseException) -> str:
    """A clear, user-facing message for an MCP connection/auth/protocol failure.

    Never interpolates the raw exception text: it can carry internal
    hostnames/ports that must not reach an API response. The full exception
    is still logged server-side by every caller of this function.
    """
    leaf = _unwrap_exception_group(exc)
    if isinstance(leaf, httpx.HTTPStatusError):
        status = leaf.response.status_code if leaf.response is not None else None
        if status in _AUTH_ERROR_STATUS_CODES:
            return f"Not authorized to reach the MCP server (HTTP {status})."
        return f"MCP server returned HTTP {status}."
    if isinstance(leaf, McpError):
        return "MCP server rejected the request."
    return "Could not connect to the MCP server."


async def get_catalog(token: str) -> dict[str, Any]:
    """Fetch the live tool catalog from the m8flow-mcp server as this caller.

    Opens a fresh MCP client session scoped to ``token`` (forwarded exactly as the
    caller's own Authorization bearer token, so tenant scoping matches what that
    user's own MCP client would see), calls ``initialize()`` then ``list_tools()``,
    and returns a flat, UI-ready summary. Never raises for connection/auth/protocol
    failures -- returns ``{"error": <message>}`` instead, mirroring the
    return-a-dict-rather-than-raise convention this codebase's controllers already
    use for outbound-call failures (see ``routes/keycloak_controller.py``).

    A missing ``M8FLOW_MCP_SERVER_URL`` carries an explicit ``"status_code":
    503`` (no outbound call is ever attempted, so it's our own
    misconfiguration, not an upstream failure) -- every other error here stays
    keyless, defaulting to 502 in ``list_mcp_tools_catalog``.
    """
    server_url = mcp_server_url()
    if not server_url:
        return {"error": "M8FLOW_MCP_SERVER_URL is not configured.", "status_code": 503}

    try:
        async with streamablehttp_client(server_url, headers=_auth_headers(token)) as (
            read_stream,
            write_stream,
            _get_session_id,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                initialize_result = await session.initialize()
                list_tools_result = await session.list_tools()
    except Exception as exc:  # connection/auth/protocol failures all land here
        logger.warning("mcp_catalog_service.get_catalog failed for %s: %s", server_url, exc)
        return {"error": _connection_error_message(exc)}

    tools = [_tool_summary(tool) for tool in list_tools_result.tools]
    return {
        "server_url": server_url,
        "protocol_version": str(initialize_result.protocolVersion),
        "tool_count": len(tools),
        "tools": tools,
    }


async def ping(token: str) -> dict[str, Any]:
    """Time a bare MCP ``initialize()`` round-trip against the server as this caller.

    ``authorized`` is ``False`` only when the failure is specifically an auth
    rejection (401/403-equivalent); it stays ``True`` on success and on any other
    failure (e.g. a network timeout or DNS error), where authorization was never
    disproven -- that's the distinction the caller needs to tell "wrong token" apart
    from "server unreachable".
    """
    server_url = mcp_server_url()
    if not server_url:
        return {"ok": False, "latency_ms": 0, "protocol_version": None, "authorized": True}

    started_at = time.monotonic()
    try:
        async with streamablehttp_client(server_url, headers=_auth_headers(token)) as (
            read_stream,
            write_stream,
            _get_session_id,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                initialize_result = await session.initialize()
    except Exception as exc:
        # NOTE: httpx exceptions (incl. HTTPStatusError for a 401/403) never reach
        # here directly -- streamablehttp_client/ClientSession run inside internal
        # anyio task groups, so they arrive wrapped in an ExceptionGroup. Catching
        # httpx.HTTPStatusError specifically would silently never match; unwrap
        # first via _http_status_from_exception instead.
        latency_ms = int((time.monotonic() - started_at) * 1000)
        status = _http_status_from_exception(exc)
        logger.warning("mcp_catalog_service.ping failed for %s: %s", server_url, exc)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "protocol_version": None,
            "authorized": status not in _AUTH_ERROR_STATUS_CODES,
        }

    latency_ms = int((time.monotonic() - started_at) * 1000)
    return {
        "ok": True,
        "latency_ms": latency_ms,
        "protocol_version": str(initialize_result.protocolVersion),
        "authorized": True,
    }


async def execute_tool(
    token: str,
    tool_name: str,
    arguments: dict[str, Any],
    confirm: bool,
) -> dict[str, Any]:
    """Call one MCP tool as this caller, enforcing the write-confirm gate.

    A single MCP session does all three round trips -- ``initialize()``,
    ``list_tools()`` (to resolve the tool and its badge), then ``tools/call`` -- so
    one execution costs one connection and one initialize, not two. The gates run
    against the freshly listed tool: an unknown ``tool_name`` is a 404, and a
    "write"-badged tool requires ``confirm`` to be exactly ``True`` before
    ``tools/call`` is ever issued. Every failure path returns an error dict shaped
    like ``{"error", "message", "status_code"}`` instead of raising, so a thin
    controller can pass it straight through as the HTTP response body/status. That
    is also why an auth rejection *by the MCP server* is reported as 502 rather
    than 401/403: the caller's own token already passed this backend's authn/RBAC,
    and answering the POST with 401 would read as an expired session client-side.

    Neither gate returns from inside the ``async with`` blocks: those run inside
    anyio task groups, where returning mid-unwind is a known source of spurious
    cancellation errors. Both instead record their outcome in ``early`` and let the
    session close normally before this returns.

    A missing ``M8FLOW_MCP_SERVER_URL`` is reported as 503, not 502, for the
    same reason as ``get_catalog``: no outbound call is ever attempted.
    """
    server_url = mcp_server_url()
    if not server_url:
        return {
            "error": "catalog_unavailable",
            "message": "M8FLOW_MCP_SERVER_URL is not configured.",
            "status_code": 503,
        }

    early: dict[str, Any] | None = None
    call_result: CallToolResult | None = None
    try:
        async with streamablehttp_client(server_url, headers=_auth_headers(token)) as (
            read_stream,
            write_stream,
            _get_session_id,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                list_tools_result = await session.list_tools()
                tool_entry = next(
                    (tool for tool in list_tools_result.tools if tool.name == tool_name), None
                )
                if tool_entry is None:
                    early = {
                        "error": "tool_not_found",
                        "message": f"No MCP tool named '{tool_name}' was found in the catalog.",
                        "status_code": 404,
                    }
                elif _tool_badge(tool_entry) == "write" and confirm is not True:
                    early = {
                        "error": "confirmation_required",
                        "message": (
                            "This tool performs a write operation and requires confirm=true to execute."
                        ),
                        "status_code": 400,
                    }
                else:
                    call_result = await session.call_tool(tool_name, arguments)
    except Exception as exc:
        # See the NOTE in ping(): unwrap before reading a status code, since httpx
        # exceptions arrive wrapped in an ExceptionGroup here too.
        #
        # An auth rejection from the separately-deployed MCP server is NOT this
        # endpoint's own 401/403: the caller's token is perfectly valid for
        # m8flow-backend (it already passed this route's own authn/RBAC) and only the
        # MCP server refused it. Forwarding 401 verbatim would make the frontend's
        # HttpService treat the POST as an expired session and bounce the admin to
        # the login page, so auth rejections are normalized to 502 -- the same status
        # get_catalog/list_mcp_tools_catalog already return for the identical
        # failure. The human-readable reason survives in "message".
        status = _http_status_from_exception(exc)
        if status is None or status in _AUTH_ERROR_STATUS_CODES:
            status = 502
        logger.warning("mcp_catalog_service.execute_tool failed for %s: %s", tool_name, exc)
        return {
            "error": "mcp_call_failed",
            "message": _connection_error_message(exc),
            "status_code": status,
        }

    if early is not None:
        return early

    if call_result is None:
        # Only reachable if the session's own task group absorbed the exception
        # raised by call_tool() (an anyio TaskGroup __aexit__ returns True when it
        # swallows a cancellation belonging to its own cancel scope). Guarding keeps
        # this function's "return an error dict, never raise" contract total.
        return {
            "error": "mcp_call_failed",
            "message": f"The MCP session closed before '{tool_name}' returned a result.",
            "status_code": 502,
        }

    if call_result.isError:
        return {
            "error": "tool_execution_error",
            "message": f"Tool '{tool_name}' reported an error.",
            "status_code": 502,
            "result": _content_blocks_to_json(call_result.content),
        }

    result_payload: Any = call_result.structuredContent
    if result_payload is None:
        result_payload = _content_blocks_to_json(call_result.content)
    return {"result": result_payload}
