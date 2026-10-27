"""Neutralise user-controlled values before they reach a log record."""

from __future__ import annotations

import re

# C0/C1 control characters (CR, LF, NEL, ESC for ANSI sequences, ...) plus the Unicode
# line/paragraph separators: anything a log viewer may render as a new line or escape.
_LOG_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def sanitize_log_value(value: object) -> str:
    """Strip control and line-separator characters so a value cannot forge log lines."""
    return _LOG_UNSAFE_RE.sub("", str(value))
