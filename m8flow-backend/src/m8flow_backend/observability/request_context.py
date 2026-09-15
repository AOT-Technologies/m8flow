"""Per-request correlation id, propagated the same way tenant id is.

Mirrors ``m8flow_backend.auth.tenant_context``'s ContextVar + ``flask.g`` + logging.Filter
pattern: a request id is assigned once per request (or taken from an
inbound ``X-Request-Id`` header so upstream proxies/tests can pin it), stored
where both request-scoped code (``flask.g``) and background/log code
(a ``ContextVar``) can read it, and echoed back on the response so a client
can hand it to support/observability tooling to find the matching Grafana
trace and log lines.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar, Token
from typing import Optional

from flask import Flask, Response, g, has_request_context, request

REQUEST_ID_HEADER = "X-Request-Id"
LOGGER = logging.getLogger(__name__)

# Polled health/status paths would dominate p99 if included.
_SKIP_DURATION_LOG_PATHS = frozenset({"/v1.0/status", "/status", "/health"})

_CONTEXT_REQUEST_ID: ContextVar[Optional[str]] = ContextVar("m8flow_request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Injects the active request id into log records for uvicorn-log.yaml."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = _CONTEXT_REQUEST_ID.get()
        if not request_id and has_request_context():
            request_id = getattr(g, "m8flow_request_id", None)
        record.m8flow_request_id = request_id or "-"
        return True


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_context_request_id(request_id: str | None) -> Token:
    return _CONTEXT_REQUEST_ID.set(request_id)


def reset_context_request_id(token: Token) -> None:
    _CONTEXT_REQUEST_ID.reset(token)


def get_context_request_id() -> str | None:
    """Return the active request id, or None outside of a request/task context."""
    if has_request_context():
        request_id = getattr(g, "m8flow_request_id", None)
        if request_id:
            return request_id
    return _CONTEXT_REQUEST_ID.get()


def install_request_id_middleware(app: Flask) -> None:
    """Assign every request a correlation id and make it available everywhere.

    - Reuses an inbound ``X-Request-Id`` header when present (so a
      gateway/load balancer id survives end to end), otherwise mints one.
    - Stores it on ``flask.g`` (request-scoped) and a ``ContextVar`` (so
      code running after the request context has been torn down, e.g. a
      ``teardown_request`` handler or a queued background call, can still
      tag its logs correctly).
    - Echoes it back via the ``X-Request-Id`` response header.
    """

    @app.before_request
    def _begin_request_id() -> None:
        incoming = (request.headers.get(REQUEST_ID_HEADER) or "").strip()
        request_id = incoming or new_request_id()
        g.m8flow_request_id = request_id
        g._m8flow_request_id_token = set_context_request_id(request_id)
        g._m8flow_request_started = time.perf_counter()
        g._m8flow_sql_query_count = 0
        g._m8flow_sql_duration_ms = 0.0

    @app.after_request
    def _echo_request_id(response: Response) -> Response:
        request_id = getattr(g, "m8flow_request_id", None)
        if request_id:
            response.headers.setdefault(REQUEST_ID_HEADER, request_id)
        started = getattr(g, "_m8flow_request_started", None)
        path = request.path or ""
        if started is not None and path not in _SKIP_DURATION_LOG_PATHS:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
            sql_query_count = int(getattr(g, "_m8flow_sql_query_count", 0) or 0)
            sql_duration_ms = round(float(getattr(g, "_m8flow_sql_duration_ms", 0.0) or 0.0), 3)
            extra: dict[str, object] = {
                "http_status": response.status_code,
                "http_method": request.method,
                "http_path": path,
                "duration_ms": duration_ms,
                "sql_query_count": sql_query_count,
                "sql_duration_ms": sql_duration_ms,
            }
            try:
                from m8flow_backend.db import get_engine

                pool = get_engine().pool
                extra["sql_pool_checkedout"] = int(pool.checkedout())
                extra["sql_pool_size"] = int(pool.size())
            except Exception:
                pass
            LOGGER.info("request completed", extra=extra)
        return response

    @app.teardown_request
    def _end_request_id(_exc: BaseException | None) -> None:
        token = getattr(g, "_m8flow_request_id_token", None)
        if token is not None:
            reset_context_request_id(token)
