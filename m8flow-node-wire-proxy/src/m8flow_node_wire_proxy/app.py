# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request

from m8flow_node_wire_proxy.adapter import execute_http_v2, execute_m8flow
from m8flow_node_wire_proxy.auth import ConnectorProxyAuthMiddleware, require_api_key_at_startup
from m8flow_node_wire_proxy.catalog import (
    HTTP_V2_COMMANDS,
    M8FLOW_COMMANDS,
    M8FLOW_CONNECTOR_IDS,
)
from m8flow_node_wire_proxy.node_wire_gateway import ensure_allowed_connectors

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_allowed_connectors()
    # Import after allowlist is set so entry-point discovery stays fail-closed.
    import node_wire_http_generic  # noqa: F401
    import node_wire_runtime  # noqa: F401

    # Warm the m8flow connectors so a missing wheel or an id absent from the
    # allowlist shows up in the startup log rather than mid-workflow. A failure
    # is logged, not fatal: the rest of the catalogue still serves.
    from m8flow_node_wire_proxy.node_wire_gateway import get_m8flow_connector

    for connector_id in sorted(set(M8FLOW_CONNECTOR_IDS.values())):
        try:
            get_m8flow_connector(connector_id)
        except ImportError as exc:
            logger.warning("m8flow connector %s unavailable: %s", connector_id, exc)

    yield


def create_app() -> FastAPI:
    """Build the ASGI app with shared-secret auth on /v1 routes."""
    api_key = require_api_key_at_startup()
    application = FastAPI(
        title="m8flow-node-wire-proxy",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(ConnectorProxyAuthMiddleware, expected_key=api_key)

    @application.get("/liveness")
    def liveness() -> dict[str, Any]:
        """Compose healthcheck target — same shape as m8flow-connector-proxy."""
        return {"ok": True}

    @application.get("/v1/commands")
    def list_commands() -> list[dict[str, Any]]:
        """Spiff-compatible operator catalog: HTTP V2 plus the m8flow connectors."""
        return [*HTTP_V2_COMMANDS, *M8FLOW_COMMANDS]

    @application.post("/v1/do/{connector}/{command}")
    async def do_command(connector: str, command: str, request: Request) -> dict[str, Any]:
        """Execute a catalogued operator; always HTTP 200 with V2 envelope."""
        raw = await request.json()
        if not isinstance(raw, dict):
            raw = {}
        if connector in M8FLOW_CONNECTOR_IDS:
            return await execute_m8flow(connector, command, raw)
        return await execute_http_v2(connector, command, raw)

    return application


app = create_app()
