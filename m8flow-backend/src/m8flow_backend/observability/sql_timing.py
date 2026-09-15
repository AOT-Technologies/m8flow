"""SQLAlchemy cursor timing for request logs and slow-query diagnosis.

Attaches to the host engine so every statement records duration. Per-request
totals ride on ``flask.g`` and are emitted on ``request completed``. Statements
slower than ``M8FLOW_SQL_SLOW_MS`` (default 100) also get their own JSON line
(``sql query slow``) with a truncated statement preview — never bind values.
"""
from __future__ import annotations

import logging
import os
import time

from sqlalchemy import Engine, event

LOGGER = logging.getLogger(__name__)

_DEFAULT_SLOW_MS = 100.0
_STATEMENT_PREVIEW_CHARS = 240
_SKIP_OPS = frozenset({"BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "SET", "SHOW", "DISCARD"})
_CURSOR_STARTS: dict[int, float] = {}


def _slow_threshold_ms() -> float | None:
    raw = (os.environ.get("M8FLOW_SQL_SLOW_MS") or "").strip()
    if raw.lower() in {"off", "none", "disabled"}:
        return None
    if not raw:
        return _DEFAULT_SLOW_MS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_SLOW_MS
    if value < 0:
        return None
    return value


def statement_operation(statement: str) -> str:
    token = (statement or "").lstrip().split(None, 1)
    return token[0].upper() if token else ""


def statement_preview(statement: str, limit: int = _STATEMENT_PREVIEW_CHARS) -> str:
    compact = " ".join((statement or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _before_cursor_execute(
    _conn,
    _cursor,
    _statement: str,
    _parameters,
    context,
    _executemany: bool,
) -> None:
    _CURSOR_STARTS[id(context)] = time.perf_counter()


def _after_cursor_execute(
    _conn,
    _cursor,
    statement: str,
    _parameters,
    context,
    _executemany: bool,
) -> None:
    started = _CURSOR_STARTS.pop(id(context), None)
    if started is None:
        return
    duration_ms = (time.perf_counter() - started) * 1000.0
    operation = statement_operation(statement)
    countable = operation not in _SKIP_OPS

    try:
        from flask import g, has_request_context

        if has_request_context():
            if countable:
                g._m8flow_sql_query_count = int(getattr(g, "_m8flow_sql_query_count", 0) or 0) + 1
            g._m8flow_sql_duration_ms = float(getattr(g, "_m8flow_sql_duration_ms", 0.0) or 0.0) + duration_ms
    except RuntimeError:
        pass

    threshold = _slow_threshold_ms()
    if threshold is None or not countable or duration_ms < threshold:
        return
    LOGGER.info(
        "sql query slow",
        extra={
            "duration_ms": round(duration_ms, 3),
            "sql_operation": operation,
            "sql_statement": statement_preview(statement),
        },
    )


def attach_sql_timing_listeners(engine: Engine) -> None:
    if event.contains(engine, "before_cursor_execute", _before_cursor_execute):
        return
    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(engine, "after_cursor_execute", _after_cursor_execute)
