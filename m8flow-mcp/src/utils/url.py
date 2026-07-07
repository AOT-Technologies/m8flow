"""URL helpers for safely embedding user-supplied values in request paths."""

from __future__ import annotations

from urllib.parse import quote


def quote_path_segment(value: str | int, safe: str = "") -> str:
    """Percent-encode a value for use inside a URL path.

    Prevents user-supplied ids containing characters like ``?``, ``#``,
    spaces, or ``/`` from altering the request path or query string.

    Args:
        value: Raw value to embed in the path.
        safe: Characters to leave unencoded (e.g. ``":"`` for modified
            process-model ids like ``group:model``).

    Returns:
        The percent-encoded path segment.
    """
    return quote(str(value), safe=safe)
