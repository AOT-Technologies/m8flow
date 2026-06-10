"""
Request-scoped connector hint for log lines (search in Loki: |~ "m8flow_connector=").
"""
from __future__ import annotations

import logging
import re
from typing import Final

# Path segments that often identify connector family in spiffworkflow-proxy routes.
_KNOWN_CONNECTOR_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "smtp",
        "slack",
        "salesforce",
        "stripe",
        "http",
        "postgres",
    }
)

_LIVENESS: Final[re.Pattern[str]] = re.compile(r"(?i)liveness|health|ready")


def infer_connector_from_path(path: str) -> str:
    if not path:
        return "none"
    if _LIVENESS.search(path):
        return "health"
    lower = path.lower()
    for token in _KNOWN_CONNECTOR_TOKENS:
        if f"/{token}" in lower or lower.endswith(f"/{token}"):
            return token
    # Fallback: first version-like prefix then next segment
    parts = [p for p in path.split("/") if p]
    for i, p in enumerate(parts):
        if p in {"v1", "v1.0", "api", "v2"} and i + 1 < len(parts):
            candidate = parts[i + 1].lower()
            if candidate in _KNOWN_CONNECTOR_TOKENS:
                return candidate
            return "other"
    return "other"


class M8flowConnectorLogFilter(logging.Filter):
    """Attach m8flow_connector to every log record (for Loki / LogQL)."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            from flask import g, has_request_context

            if has_request_context() and hasattr(g, "m8flow_connector"):
                record.m8flow_connector = g.m8flow_connector  # type: ignore[attr-defined]
            else:
                record.m8flow_connector = "-"
        except Exception:  # pragma: no cover
            record.m8flow_connector = "-"
        return True
