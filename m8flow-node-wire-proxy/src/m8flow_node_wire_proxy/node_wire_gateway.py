# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
"""Single seam for the node-wire import-ordering invariant.

node-wire's entry-point discovery reads NW_ALLOWED_CONNECTORS at import time
and fails closed if it isn't set. Every site that imports node_wire_* must
set the allowlist first, or the allowlist silently stops applying. This
module is the one place that rule lives — app.lifespan and the adapter's
outbound-request connectors all depend on it instead of repeating it.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

_DEFAULT_ALLOWED_CONNECTORS = "http_generic"


def ensure_allowed_connectors() -> None:
    """Fail-closed node-wire allowlist — HTTP connector only for this host.

    Uses setdefault so an operator-provided NW_ALLOWED_CONNECTORS is never
    overridden.
    """
    os.environ.setdefault("NW_ALLOWED_CONNECTORS", _DEFAULT_ALLOWED_CONNECTORS)


def get_http_generic_connector() -> type[Any]:
    """Return HttpGenericConnector, importing only after the allowlist is set."""
    ensure_allowed_connectors()
    from node_wire_http_generic.logic import HttpGenericConnector

    return HttpGenericConnector


def get_ssrf_gate() -> tuple[Callable[[str], Awaitable[None]], type[Exception]] | None:
    """Return (assert_safe_destination, SsrfBlockedError), or None if unavailable.

    http_generic's SSRF gate is a private symbol. Callers must treat a None
    result as "refuse the request" — never as "skip the check".
    """
    ensure_allowed_connectors()
    try:
        from node_wire_http_generic.logic import SsrfBlockedError, _assert_safe_destination
    except ImportError:
        return None
    return _assert_safe_destination, SsrfBlockedError
