# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
"""Map Spiff wire calls onto node-wire connectors.

Two execute paths, both returning the same V2 envelope:

* ``execute_http_v2`` -- the HTTP V2 operators, mapped onto http_generic.
* ``execute_m8flow``  -- the m8flow connectors, which take their parameters
  as-is rather than through an HTTP request shape.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from m8flow_node_wire_proxy.catalog import (
    M8FLOW_ACTIONS,
    M8FLOW_CONNECTOR_IDS,
    M8FLOW_PARAM_NAMES,
    OPERATOR_METHODS,
)

_SPIFF_PREFIX = "spiff__"

# node-wire ErrorCategory -> HTTP status for the V2 envelope. A caller that
# branches on http_status should see a retryable fault as 503 and an auth
# failure as 401, the same way the connector's own REST surface reports them.
_CATEGORY_STATUS: dict[str, int] = {
    "RETRYABLE": 503,
    "BUSINESS": 400,
    "AUTH": 401,
    "FATAL": 500,
}


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


def _message_with_details(message: str | None, details: Any) -> str | None:
    """Fold node-wire's per-field details into the message.

    The runtime reports a validation failure as the generic "Input validation
    failed; please check the request payload." and puts the offending field in
    ``details``. The envelope carries no details slot, so a modeler otherwise
    sees nothing actionable -- append them.
    """
    if not isinstance(details, list) or not details:
        return message
    parts = []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        text = str(detail.get("msg") or "").strip()
        if not text:
            continue
        loc = detail.get("loc")
        field = ".".join(str(x) for x in loc) if isinstance(loc, (list, tuple)) else loc
        parts.append(f"{field}: {text}" if field else text)
    if not parts:
        return message
    joined = "; ".join(parts)
    return f"{message} ({joined})" if message else joined


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


def build_m8flow_input(command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return the connector-input dict for a catalogued m8flow command.

    Only catalogued parameters survive. The m8flow input models set
    extra="forbid", so an undeclared key would fail the whole call -- and a
    Service Task carries editor-supplied keys the connector never declared.
    Empty values are dropped too: an unfilled optional operator parameter
    arrives as "" and would fail a typed field such as smtp_port.
    """
    action = M8FLOW_ACTIONS[command_id]
    declared = M8FLOW_PARAM_NAMES[command_id]
    request_input: dict[str, Any] = {"action": action}
    for name, value in payload.items():
        if name not in declared:
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        request_input[name] = value
    return request_input


def envelope_from_connector_response(response: Any) -> dict[str, Any]:
    """Map a node-wire ConnectorResponse onto the Spiff V2 envelope.

    A connector that reports failure as data keeps success=True and lands in
    the body -- m8flow_n8n does this deliberately, because a top-level error
    suspends the process instance and hangs the UI.
    """
    if response.success:
        return {
            "command_response": {
                "body": response.data if response.data is not None else {},
                "mimetype": "application/json",
                "http_status": 200,
            },
            "error": None,
            "command_response_version": 2,
        }

    category = getattr(response.error_category, "value", response.error_category)
    return envelope_from_connector_failure(
        error_code=response.error_code,
        message=_message_with_details(response.message, getattr(response, "details", None)),
        http_status=_CATEGORY_STATUS.get(str(category), 500),
    )


async def execute_m8flow(connector: str, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute one catalogued m8flow connector action."""
    connector_id = M8FLOW_CONNECTOR_IDS.get(connector)
    if connector_id is None:
        return envelope_from_connector_failure(
            error_code="UnknownConnector",
            message=f"unsupported connector '{connector}'",
        )

    command_id = f"{connector}/{command}"
    if command_id not in M8FLOW_ACTIONS:
        return envelope_from_connector_failure(
            error_code="UnknownCommand",
            message=f"unsupported command '{command}' for connector '{connector}'",
        )

    request_input = build_m8flow_input(command_id, strip_spiff_keys(payload))

    from m8flow_node_wire_proxy.node_wire_gateway import get_m8flow_connector

    try:
        connector_cls = get_m8flow_connector(connector_id)
    except ImportError as exc:
        # Installed wheel missing, or the id is absent from NW_ALLOWED_CONNECTORS
        # (the node-wire registry is fail-closed).
        return envelope_from_connector_failure(
            error_code="ConnectorUnavailable",
            message=f"connector '{connector_id}' is not installed or not allowed: {exc}",
        )

    response = await connector_cls().run(request_input)
    return envelope_from_connector_response(response)
