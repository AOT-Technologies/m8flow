"""Neutralise user-controlled values before they reach a log record."""

from __future__ import annotations


def sanitize_log_value(value: object) -> str:
    """Strip CR/LF so a user-supplied value cannot forge extra log lines."""
    return str(value).replace("\r", "").replace("\n", "")
