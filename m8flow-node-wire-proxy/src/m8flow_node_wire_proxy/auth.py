# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
"""Shared-secret gate for connector-proxy /v1 routes.

The backend→proxy contract is machine-to-machine. Callers must present
``X-M8FLOW-Connector-Proxy-Key`` matching ``M8FLOW_CONNECTOR_PROXY_API_KEY``.
``/liveness`` stays open for compose healthchecks.
"""

from __future__ import annotations

import hmac
import os
from typing import Final

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

API_KEY_ENV: Final = "M8FLOW_CONNECTOR_PROXY_API_KEY"
API_KEY_HEADER: Final = "X-M8FLOW-Connector-Proxy-Key"
# Test-only escape hatch (pytest sets this). Never enable in deployed stacks.
ALLOW_UNAUTHENTICATED_ENV: Final = "NW_ALLOW_UNAUTHENTICATED"


def configured_api_key() -> str:
    return (os.environ.get(API_KEY_ENV) or "").strip()


def allow_unauthenticated() -> bool:
    return (os.environ.get(ALLOW_UNAUTHENTICATED_ENV) or "").strip() == "1"


def require_api_key_at_startup() -> str:
    """Return the configured key, or empty when unauthenticated mode is allowed.

    Outside the test escape hatch, refuse to boot without an explicit secret so
    an incomplete env cannot leave /v1/do open as an outbound HTTP relay.
    """
    key = configured_api_key()
    if key:
        return key
    if allow_unauthenticated():
        return ""
    raise RuntimeError(
        f"{API_KEY_ENV} must be set (shared secret for /v1 connector routes). "
        f"Set {ALLOW_UNAUTHENTICATED_ENV}=1 only for local unit tests."
    )


def _header_key(request: Request) -> str:
    return (request.headers.get(API_KEY_HEADER) or "").strip()


def unauthorized_response() -> JSONResponse:
    return JSONResponse({"detail": "Unauthorized"}, status_code=401)


def request_is_authorized(request: Request, *, expected_key: str) -> bool:
    if not expected_key:
        # Startup allowed unauthenticated mode (tests only).
        return True
    presented = _header_key(request)
    return bool(presented) and hmac.compare_digest(presented, expected_key)


class ConnectorProxyAuthMiddleware(BaseHTTPMiddleware):
    """Require the shared API key on /v1/*; leave /liveness public."""

    def __init__(self, app, *, expected_key: str) -> None:
        super().__init__(app)
        self._expected_key = expected_key

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path == "/liveness" or path.startswith("/liveness/"):
            return await call_next(request)
        if path.startswith("/v1/") or path == "/v1":
            if not request_is_authorized(request, expected_key=self._expected_key):
                return unauthorized_response()
        return await call_next(request)
