"""Liveness/readiness probes for load balancers and container orchestration.

Relocated from tenancy.py during the active-tenant deep-module collapse
(ticket 03): health/readiness has nothing to do with tenant resolution.
"""
from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)


def get_healthy_response() -> tuple[dict, int]:
    """Return the canonical liveness response (payload, status_code)."""
    return ({"status": "ok", "ok": True, "healthy": True}, 200)


def get_ready_response() -> tuple[dict, int]:
    """Return 200 when the database answers SELECT 1, else 503."""
    from sqlalchemy import text

    from m8flow_backend.db import get_engine

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        LOGGER.exception("Readiness probe: database unreachable")
        return ({"status": "unavailable", "ok": False, "healthy": False}, 503)
    return ({"status": "ok", "ok": True, "healthy": True}, 200)


def health_check():
    """Public liveness check for load balancers. Returns 200 when the process is up."""
    return get_healthy_response()
