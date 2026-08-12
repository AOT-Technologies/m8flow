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

from m8flow_backend.config import mcp_server_url

logger = logging.getLogger(__name__)

# Tool names disabled for MCP clients tenant-wide. Currently empty: no shipped MCP
# tool ships as sensitive yet. This is the seam a future "Manage permissions" admin
# toggle will populate -- execute_tool() is the single enforcement point that reads
# this constant, so that future ticket has one obvious place to replace it.
SENSITIVE_TOOL_NAMES: frozenset[str] = frozenset()

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
    """"sensitive" if tenant-disabled via SENSITIVE_TOOL_NAMES; else "read" when the
    tool's annotations mark it read-only, else "write".

    Checked first: a sensitive tool is sensitive regardless of its readOnlyHint, and
    the catalog UI needs this in the badge itself to render the locked state -- the
    write-confirm vs. sensitive-disabled distinction is exactly what tells the UI
    which of "Try it" or the locked message to show for a given tool.
    """
    if tool.name in SENSITIVE_TOOL_NAMES:
        return "sensitive"
    annotations = getattr(tool, "annotations", None)
    read_only_hint = getattr(annotations, "readOnlyHint", None) if annotations is not None else None
    return "read" if read_only_hint is True else "write"


def _tool_parameters(tool: Any) -> list[dict[str, Any]]:
    """Derive the catalog's parameter list from a tool's JSON-Schema inputSchema."""
    schema = getattr(tool, "inputSchema", None) or {}
    properties = schema.get("properties") or {}
    required_names = set(schema.get("required") or [])

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


def _tool_summary(tool: Any) -> dict[str, Any]:
    """Catalog entry for one MCP tool: display metadata plus derived parameters."""
    tags = _tool_tags(tool)
    return {
        "name": tool.name,
        "description": tool.description or "",
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
    """A clear, user-facing message for an MCP connection/auth/protocol failure."""
    leaf = _unwrap_exception_group(exc)
    if isinstance(leaf, httpx.HTTPStatusError):
        status = leaf.response.status_code if leaf.response is not None else None
        if status in _AUTH_ERROR_STATUS_CODES:
            return f"Not authorized to reach the MCP server (HTTP {status})."
        return f"MCP server returned HTTP {status}."
    if isinstance(leaf, McpError):
        return f"MCP server rejected the request: {leaf}"
    return f"Could not connect to the MCP server: {leaf}"


async def get_catalog(token: str) -> dict[str, Any]:
    """Fetch the live tool catalog from the m8flow-mcp server as this caller.

    Opens a fresh MCP client session scoped to ``token`` (forwarded exactly as the
    caller's own Authorization bearer token, so tenant scoping matches what that
    user's own MCP client would see), calls ``initialize()`` then ``list_tools()``,
    and returns a flat, UI-ready summary. Never raises for connection/auth/protocol
    failures -- returns ``{"error": <message>}`` instead, mirroring the
    return-a-dict-rather-than-raise convention this codebase's controllers already
    use for outbound-call failures (see ``routes/keycloak_controller.py``).
    """
    server_url = mcp_server_url()
    if not server_url:
        return {"error": "M8FLOW_MCP_SERVER_URL is not configured."}

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
    """Call one MCP tool as this caller, enforcing the sensitive/write-confirm gates.

    Order of checks: (1) ``tool_name`` is not tenant-disabled via
    ``SENSITIVE_TOOL_NAMES`` -- a local, no-network check, so it never wastes a
    round trip on a tool nobody may run; (2) the catalog's badge for the tool is
    "write" implies ``confirm`` must be exactly ``True``. Only once both pass does
    this issue ``tools/call``. Every failure path returns an error dict shaped like
    ``{"error", "message", "status_code"}`` instead of raising, so a thin controller
    can pass it straight through as the HTTP response body/status.
    """
    if tool_name in SENSITIVE_TOOL_NAMES:
        return {
            "error": "sensitive_tool_disabled",
            "message": "Disabled for MCP clients in this tenant. Enable it under Manage permissions.",
            "status_code": 403,
        }

    catalog = await get_catalog(token)
    if "error" in catalog:
        return {
            "error": "catalog_unavailable",
            "message": catalog["error"],
            "status_code": 502,
        }

    tool_entry = next((entry for entry in catalog["tools"] if entry["name"] == tool_name), None)
    if tool_entry is None:
        return {
            "error": "tool_not_found",
            "message": f"No MCP tool named '{tool_name}' was found in the catalog.",
            "status_code": 404,
        }

    if tool_entry["badge"] == "write" and confirm is not True:
        return {
            "error": "confirmation_required",
            "message": "This tool performs a write operation and requires confirm=true to execute.",
            "status_code": 400,
        }

    server_url = mcp_server_url()
    try:
        async with streamablehttp_client(server_url, headers=_auth_headers(token)) as (
            read_stream,
            write_stream,
            _get_session_id,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                call_result = await session.call_tool(tool_name, arguments)
    except Exception as exc:
        # See the NOTE in ping(): unwrap before reading a status code, since httpx
        # exceptions arrive wrapped in an ExceptionGroup here too.
        status = _http_status_from_exception(exc) or 502
        logger.warning("mcp_catalog_service.execute_tool failed for %s: %s", tool_name, exc)
        return {
            "error": "mcp_call_failed",
            "message": _connection_error_message(exc),
            "status_code": status,
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
