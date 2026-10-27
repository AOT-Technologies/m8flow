"""Neutralise user-controlled values before they reach a log record."""

from __future__ import annotations

import re

# Other C0/C1 controls (NEL, ESC for ANSI sequences, ...) and the Unicode line/paragraph
# separators: anything a log viewer may render as a new line or escape sequence.
_LOG_UNSAFE_RE = re.compile(r"[\x00-\x09\x0b\x0c\x0e-\x1f\x7f-\x9f  ]")


def sanitize_log_value(value: object) -> str:
    """Strip control and line-separator characters so a value cannot forge log lines."""
    # CR/LF go through str.replace on purpose: that is the form CodeQL's py/log-injection
    # query recognises as a sanitizer (a regex alone is not), so keep it as the last step.
    return _LOG_UNSAFE_RE.sub("", str(value)).replace("\r", "").replace("\n", "")
