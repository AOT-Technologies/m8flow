"""Wire m8flow-backend into the shared OTel bootstrap (m8flow_telemetry).

Same call shape as m8flow-connector-proxy and m8flow-nats-consumer: opt-in via
OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_SDK_DISABLED (see m8flow_telemetry.bootstrap
docstrings), targeting the Grafana Alloy OTLP collector in sample.env. Kept
defensive on purpose — a telemetry misconfiguration (bad endpoint, missing
optional instrumentation package) must degrade to "no telemetry", never take
the whole backend down.
"""
from __future__ import annotations

import logging

from flask import Flask

from m8flow_backend.auth.tenant_context import get_context_tenant_id

LOGGER = logging.getLogger(__name__)


def install_telemetry(app: Flask) -> bool:
    """Configure OTel traces/metrics/logs and instrument the Flask app.

    Returns True when export is active, False when telemetry is disabled or
    failed to initialize (backend keeps running either way).
    """
    try:
        from m8flow_telemetry.bootstrap import instrument_flask_app, is_telemetry_enabled, setup

        setup("m8flow-backend", tenant_resolver=get_context_tenant_id)
        instrument_flask_app(app)
        enabled = is_telemetry_enabled()
        if enabled:
            LOGGER.info("OpenTelemetry export enabled for m8flow-backend.")
        else:
            LOGGER.info("OpenTelemetry export disabled (OTEL_SDK_DISABLED or no OTEL_EXPORTER_OTLP_ENDPOINT).")
        return enabled
    except Exception:
        LOGGER.exception("Failed to initialize OpenTelemetry; continuing without export.")
        return False
