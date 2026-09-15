# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
"""Map Spiff HTTP V2 wire calls onto node-wire http_generic.request."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from m8flow_node_wire_proxy.catalog import OPERATOR_METHODS

_SPIFF_PREFIX = "spiff__"


@dataclass
class ConnectorResult:
    """Uniform result shape both outbound-request adapters return.

    Lets execute_http_v2's retry loop stay ignorant of which adapter ran —
    http_generic (node-wire, in-process) and the hand-rolled HEAD adapter
    both normalize into this before returning.
    """

    success: bool
    data: dict[str, Any] | None
    error_code: str | None
    message: str | None


def strip_spiff_keys(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if not str(k).startswith(_SPIFF_PREFIX)}


def _coerce_str_dict(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("headers/params must be an object")
    return {str(k): "" if v is None else str(v) for k, v in value.items()}


def _normalize_attempts(raw: Any) -> int:
    if not isinstance(raw, int) or raw < 1 or raw > 10:
        return 1
    return raw


def _inject_basic_auth(headers: dict[str, str], username: Any, password: Any) -> None:
    if username is None or password is None:
        return
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    headers["Authorization"] = f"Basic {token}"


def build_http_generic_input(command: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return (HttpRequestInput-shaped dict, attempts)."""
    method = OPERATOR_METHODS.get(command)
    if method is None:
        raise KeyError(command)

    url = payload.get("url")
    if not url or not isinstance(url, str):
        raise ValueError("url is required and must be a string")

    headers = _coerce_str_dict(payload.get("headers")) or {}
    _inject_basic_auth(headers, payload.get("basic_auth_username"), payload.get("basic_auth_password"))

    params = _coerce_str_dict(payload.get("params")) if method in {"GET", "HEAD", "DELETE"} else None
    body = payload.get("data") if method in {"POST", "PUT", "PATCH", "DELETE"} else None

    attempts = _normalize_attempts(payload.get("attempts")) if method in {"GET", "HEAD"} else 1

    request_input: dict[str, Any] = {
        "action": "request",
        "url": url,
        "method": method,
        "headers": headers or None,
        "params": params,
        "body": body,
    }
    return request_input, attempts


def _parse_body(text: str, response_headers: dict[str, Any]) -> tuple[Any, dict[str, Any] | None]:
    """Match Spiff HttpRequestBase JSON parsing (skip XML)."""
    content_type = ""
    for key, value in response_headers.items():
        if key.lower() == "content-type":
            content_type = str(value)
            break

    body: Any = {"raw_response": text}
    error: dict[str, Any] | None = None
    if "application/json" in content_type:
        try:
            body = json.loads(text) if text else None
        except Exception as exc:  # noqa: BLE001 — mirror Spiff catch-all parse errors
            error = {
                "error_code": type(exc).__name__,
                "message": f"Received Error: {exc}. Raw http_response was: {text}",
            }
    return body, error


def envelope_from_http_result(
    *,
    status_code: int,
    response_headers: dict[str, Any],
    body_text: str,
    prior_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body, parse_error = _parse_body(body_text, response_headers)
    error = prior_error or parse_error
    if error is None and status_code >= 400:
        error = {
            "error_code": f"HttpError{status_code}",
            "message": f"Received Error: . Raw http_response was: {body_text}",
        }
    return {
        "command_response": {
            "body": body,
            "mimetype": "application/json",
            "http_status": status_code,
        },
        "error": error,
        "command_response_version": 2,
    }


def envelope_from_connector_failure(
    *,
    error_code: str | None,
    message: str | None,
    http_status: int = 500,
) -> dict[str, Any]:
    return {
        "command_response": {
            "body": {},
            "mimetype": "application/json",
            "http_status": http_status,
        },
        "error": {
            "error_code": error_code or "ConnectorError",
            "message": message or "connector execution failed",
        },
        "command_response_version": 2,
    }


async def _run_http_generic(request_input: dict[str, Any]) -> ConnectorResult:
    """http_generic (node-wire, in-process) — every method except HEAD.

    HEAD is not allowed by http_generic's schema — see _run_head.
    """
    from m8flow_node_wire_proxy.node_wire_gateway import get_http_generic_connector

    HttpGenericConnector = get_http_generic_connector()
    response = await HttpGenericConnector().run(dict(request_input))
    return ConnectorResult(
        success=bool(response.success),
        data=response.data or {},
        error_code=response.error_code,
        message=response.message,
    )


async def _run_head(request_input: dict[str, Any]) -> ConnectorResult:
    """Adapter-side HEAD (http_generic disallows HEAD method).

    Fails closed: if http_generic's SSRF gate isn't available, the request
    is refused rather than sent unchecked.
    """
    from m8flow_node_wire_proxy.node_wire_gateway import get_ssrf_gate

    gate = get_ssrf_gate()
    if gate is None:
        return ConnectorResult(
            success=False,
            data=None,
            error_code="SsrfGateUnavailable",
            message="SSRF gate unavailable, refusing HEAD request",
        )
    assert_safe_destination, ssrf_blocked_error = gate

    try:
        await assert_safe_destination(str(request_input["url"]))
    except ssrf_blocked_error as exc:
        return ConnectorResult(success=False, data=None, error_code="SsrfBlockedError", message=str(exc))

    timeout = float(os.getenv("NW_TIMEOUT", "30.0"))
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            response = await client.request(
                method="HEAD",
                url=str(request_input["url"]),
                headers=request_input.get("headers"),
                params=request_input.get("params"),
                timeout=timeout,
            )
    except Exception as exc:  # noqa: BLE001 — map transport errors like Spiff
        return ConnectorResult(success=False, data=None, error_code=type(exc).__name__, message=str(exc))

    return ConnectorResult(
        success=True,
        data={
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text or "",
        },
        error_code=None,
        message=None,
    )


_CONNECTORS: dict[str, Callable[[dict[str, Any]], Awaitable[ConnectorResult]]] = {
    "HEAD": _run_head,
}


def _connector_for(method: str) -> Callable[[dict[str, Any]], Awaitable[ConnectorResult]]:
    """Dispatch table: HEAD gets the hand-rolled adapter, everything else goes through http_generic."""
    return _CONNECTORS.get(method, _run_http_generic)


async def execute_http_v2(connector: str, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    if connector != "http":
        return envelope_from_connector_failure(
            error_code="UnknownConnector",
            message=f"unsupported connector '{connector}' (HTTP V2 POC only)",
        )
    if command not in OPERATOR_METHODS:
        return envelope_from_connector_failure(
            error_code="UnknownCommand",
            message=f"unsupported command '{command}'",
        )

    clean = strip_spiff_keys(payload)
    try:
        request_input, attempts = build_http_generic_input(command, clean)
    except (KeyError, ValueError) as exc:
        return envelope_from_connector_failure(error_code=type(exc).__name__, message=str(exc))

    method = request_input["method"]
    run_connector = _connector_for(method)
    last_envelope: dict[str, Any] | None = None

    for attempt in range(1, attempts + 1):
        if attempt > 1:
            await asyncio.sleep(1)

        result = await run_connector(request_input)
        if not result.success:
            return envelope_from_connector_failure(error_code=result.error_code, message=result.message)

        data = result.data or {}
        status = int(data.get("status_code") or 0)
        headers = data.get("headers") or {}
        body_text = data.get("body")
        if body_text is None:
            body_text = ""
        elif not isinstance(body_text, str):
            body_text = json.dumps(body_text)

        last_envelope = envelope_from_http_result(
            status_code=status,
            response_headers=headers,
            body_text=body_text,
        )
        # Spiff retries only on 5xx for Get/Head.
        if status // 100 != 5:
            break

    assert last_envelope is not None
    return last_envelope
