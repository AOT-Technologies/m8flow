from __future__ import annotations

import logging
import os
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from m8flow_telemetry.context import TenantResolver, default_tenant_resolver
from m8flow_telemetry.logging_bridge import (
    M8FLOW_TENANT_ID_ATTR,
    StdlibTenantFilter,
    TenantAttributeLogProcessor,
)

_CONFIGURED = False
_METER: Any = None


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _otlp_endpoint() -> str | None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        return endpoint
    if _env_truthy("OTEL_SDK_DISABLED"):
        return None
    # Default when observability stack is running on the shared docker network.
    return os.getenv("M8FLOW_OTEL_EXPORTER_OTLP_ENDPOINT", "http://m8flow-alloy:4317")


def is_telemetry_enabled() -> bool:
    if _env_truthy("OTEL_SDK_DISABLED"):
        return False
    return bool(_otlp_endpoint())


def _build_resource(service_name: str) -> Resource:
    deployment_env = os.getenv("M8FLOW_BACKEND_ENV") or os.getenv("DEPLOYMENT_ENVIRONMENT") or "local_development"
    return Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": deployment_env,
        }
    )


def get_meter() -> Any:
    global _METER
    if _METER is None:
        _METER = metrics.get_meter("m8flow.telemetry")
    return _METER


def setup(
    service_name: str,
    *,
    tenant_resolver: TenantResolver | None = None,
    enable_logs: bool = True,
    enable_traces: bool = True,
    enable_metrics: bool = True,
) -> bool:
    """Configure OTel logs/metrics/traces. Returns True when export is active."""
    global _CONFIGURED
    if _CONFIGURED:
        return is_telemetry_enabled()

    endpoint = _otlp_endpoint()
    if not endpoint or _env_truthy("OTEL_SDK_DISABLED"):
        _CONFIGURED = True
        return False

    resolver = tenant_resolver or default_tenant_resolver
    resource = _build_resource(service_name)

    if enable_traces:
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
        )
        trace.set_tracer_provider(tracer_provider)

    if enable_metrics:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=True),
            export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "60000")),
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)

    if enable_logs:
        log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=True)
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(TenantAttributeLogProcessor(resolver))
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        from opentelemetry._logs import set_logger_provider

        set_logger_provider(logger_provider)
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
        handler.addFilter(StdlibTenantFilter(resolver))
        handler.__dict__["_m8flow_otel_logging_handler"] = True
        logging.getLogger().addHandler(handler)

    _CONFIGURED = True
    return True


def instrument_flask_app(app: Any) -> None:
    if not is_telemetry_enabled():
        return
    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.wsgi import WSGIInstrumentor
    except ImportError:
        return

    FlaskInstrumentor().instrument_app(app)
    WSGIInstrumentor().instrument()
    RequestsInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()


def instrument_asgi_app(app: Any) -> Any:
    if not is_telemetry_enabled():
        return app
    try:
        from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    except ImportError:
        return app

    HTTPXClientInstrumentor().instrument()
    return OpenTelemetryMiddleware(app)


def tenant_metric_attributes(tenant_id: str | None) -> dict[str, str]:
    if not tenant_id:
        return {}
    return {M8FLOW_TENANT_ID_ATTR: tenant_id}
