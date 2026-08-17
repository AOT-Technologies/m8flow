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

    Mirrors ``NatsService._run_coroutine`` exactly: reuse the running loop via a
    worker thread if one is somehow already running (a normal Flask WSGI worker
    never has one, but this stays correct if that ever changes), else fall back
    to a fresh ``asyncio.run``.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if loop.is_running():
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor() as executor:
            return executor.submit(asyncio.run, coro).result()
    return loop.run_until_complete(coro)


def _bearer_token() -> str:
    """The calling user's own bearer token, taken as-is from the Authorization header.

    Passed straight through: ``mcp_catalog_service._auth_headers()`` strips a
    leading "Bearer " itself, so it does not matter whether one is present here.
    """
    return request.headers.get("Authorization") or ""


def list_mcp_tools_catalog() -> flask.wrappers.Response:
    """GET /m8flow/mcp-tools -- the live MCP tool catalog, as this caller."""
    result = _run_coroutine(mcp_catalog_service.get_catalog(_bearer_token()))
    if "error" in result:
        return error_response("mcp_catalog_unavailable", result["error"], 502)
    return make_response(jsonify(result), 200)


def check_mcp_connection() -> flask.wrappers.Response:
    """GET /m8flow/mcp-tools/ping -- a bare connectivity/auth check, as this caller."""
    result = _run_coroutine(mcp_catalog_service.ping(_bearer_token()))
    return make_response(jsonify(result), 200)


def execute_mcp_tool(body: dict[str, Any]) -> flask.wrappers.Response:
    """POST /m8flow/mcp-tools/execute -- call one MCP tool, as this caller.

    Body: ``{"tool_name": "...", "arguments": {...}, "confirm": bool}``. The
    service enforces the write-confirm gate and returns
    ``{"error", "message", "status_code"}`` on any rejection -- that
    ``status_code`` (400 missing confirm for a write-badged tool, 404 unknown
    tool, 502 MCP call failure) is passed straight through as the HTTP status
    code. An auth rejection by the MCP server itself is normalized to 502 by the
    service, so it never surfaces here as this endpoint's own 401/403.
    """
    tool_name = body.get("tool_name")
    arguments = body.get("arguments") or {}
    confirm = body.get("confirm", False)

    result = _run_coroutine(
        mcp_catalog_service.execute_tool(_bearer_token(), tool_name, arguments, confirm)
    )
    if "error" in result:
        status_code = result.get("status_code", 400)
        return error_response(result["error"], result.get("message", ""), status_code)
    return make_response(jsonify(result), 200)
