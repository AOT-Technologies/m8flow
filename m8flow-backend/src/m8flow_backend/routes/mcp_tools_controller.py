"""MCP tools admin endpoints: catalog, connection check, and tool execution.

Thin Connexion operation functions over ``services.mcp_catalog_service``. Every
function forwards the CALLING USER'S OWN bearer token straight from the incoming
request's ``Authorization`` header -- the same header this codebase's other
bearer-token readers use (e.g. ``authentication_service_patch.py``) -- so the
service sees exactly what a real MCP client acting on that user's behalf would
see. ``mcp_catalog_service``'s functions are ``async`` (each opens its own MCP
client session); Connexion here still runs these operation functions
synchronously under Flask's WSGI stack, so ``_run_coroutine`` bridges the two --
mirroring ``NatsService._run_coroutine`` in ``services/nats_service.py``, the
existing precedent in this codebase for calling async code from a sync route.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import flask.wrappers
from flask import jsonify, make_response, request

from m8flow_backend.helpers.response_helper import error_response
from m8flow_backend.services import mcp_catalog_service

logger = logging.getLogger(__name__)


def _run_coroutine(coro: Any) -> Any:
    """Run an async coroutine to completion from this synchronous Flask view.

    Sync-only by contract. Connexion runs these operation functions under
    Flask's WSGI stack, where this thread has no running event loop, so
    ``asyncio.run`` owns a fresh loop for the call's duration.

    If a loop *is* already running on this thread we refuse loudly instead of
    offloading to a worker thread and blocking on its future: that blocks the
    running loop for a full MCP network round-trip, starving every other task
    on it. Whoever makes this thread async must make these views ``async def``
    and await ``mcp_catalog_service``'s coroutines directly rather than
    bridging through here.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Reached only from a thread that already drives a loop. Close the
    # coroutine first so refusing does not also emit "never awaited".
    coro.close()
    raise RuntimeError(
        "mcp_tools_controller._run_coroutine was called from a thread with a "
        "running event loop. These views are sync-only; await "
        "mcp_catalog_service's coroutines directly instead."
    )


def _bearer_token() -> str:
    """The calling user's own bearer token, taken as-is from the Authorization header.

    Passed straight through: ``mcp_catalog_service._auth_headers()`` strips a
    leading "Bearer " itself, so it does not matter whether one is present here.
    """
    return request.headers.get("Authorization") or ""


def list_mcp_tools_catalog() -> flask.wrappers.Response:
    """GET /m8flow/mcp-tools -- the live MCP tool catalog, as this caller.

    ``get_catalog`` returns an explicit ``status_code`` (503) only for its
    self-inflicted failure -- ``M8FLOW_MCP_SERVER_URL`` not configured; every
    other failure is keyless and defaults to 502 here.
    """
    result = _run_coroutine(mcp_catalog_service.get_catalog(_bearer_token()))
    if "error" in result:
        return error_response("mcp_catalog_unavailable", result["error"], result.get("status_code", 502))
    return make_response(jsonify(result), 200)


def check_mcp_connection() -> flask.wrappers.Response:
    """GET /m8flow/mcp-tools/ping -- a bare connectivity/auth check, as this caller.

    Always 200, deliberately -- unlike ``list_mcp_tools_catalog`` and
    ``execute_mcp_tool``, which surface 502/503 for the same underlying MCP
    failures. This endpoint's job is to *report* reachability, so "unreachable"
    is its expected answer rather than a failed request; ``ping`` never returns
    an "error" key, only ``{ok, latency_ms, protocol_version, authorized}``.

    Do not "fix" this to 502/503 without changing the caller in lockstep:
    m8flow-frontend's McpToolsCatalog renders the failure state (the "ping
    failed" line and the unauthorized chip) from that body, and HttpService
    routes any non-2xx to failureCallback, which nulls the ping state and hides
    that UI entirely -- so returning a failure status erases the very
    diagnostic this endpoint exists to show.
    """
    result = _run_coroutine(mcp_catalog_service.ping(_bearer_token()))
    return make_response(jsonify(result), 200)


def execute_mcp_tool(body: dict[str, Any] | None) -> flask.wrappers.Response:
    """POST /m8flow/mcp-tools/execute -- call one MCP tool, as this caller.

    Body: ``{"tool_name": "...", "arguments": {...}, "confirm": bool}``. The
    service enforces the write-confirm gate and returns
    ``{"error", "message", "status_code"}`` on any rejection -- that
    ``status_code`` (400 missing confirm for a write-badged tool, 404 unknown
    tool, 502 MCP call failure) is passed straight through as the HTTP status
    code. An auth rejection by the MCP server itself is normalized to 502 by the
    service, so it never surfaces here as this endpoint's own 401/403.

    api.yml's requestBody schema validates shape (object body, non-empty
    tool_name, object arguments), but that runs in Connexion's request
    pipeline, not in this function, so each is guarded explicitly below too.
    """
    if not isinstance(body, dict):
        return error_response(
            "invalid_request_body",
            "Request body must be a JSON object with a 'tool_name' field.",
            400,
        )

    tool_name = body.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return error_response(
            "invalid_request_body",
            "The 'tool_name' field must be a non-empty string.",
            400,
        )

    arguments = body.get("arguments") or {}
    if not isinstance(arguments, dict):
        return error_response(
            "invalid_request_body",
            "The 'arguments' field must be a JSON object.",
            400,
        )
    confirm = body.get("confirm", False)

    result = _run_coroutine(
        mcp_catalog_service.execute_tool(_bearer_token(), tool_name, arguments, confirm)
    )
    if "error" in result:
        status_code = result.get("status_code", 400)
        return error_response(result["error"], result.get("message", ""), status_code)
    return make_response(jsonify(result), 200)
