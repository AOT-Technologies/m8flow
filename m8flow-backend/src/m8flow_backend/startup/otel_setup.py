# m8flow_backend/startup/otel_setup.py
import logging
import os

logger = logging.getLogger(__name__)

_otel_state: dict[str, bool] = {
    "setup_in_progress": False,
    "traces": False,
    "logs": False,
    "metrics": False,
    "instrumentation": False,
}
_otel_logging_handler: logging.Handler | None = None


def _root_logger_has_handler(handler_type: type, *, marker_attr: str | None = None) -> bool:
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, handler_type):
            if marker_attr is None or getattr(h, marker_attr, False):
                return True
    return False


def setup_otel(app) -> None:
    """Set up OpenTelemetry traces, logs, and metrics if OTLP endpoint is configured.

    Idempotent across repeated calls in-process. If setup partially succeeds and then
    fails, subsequent calls will continue with remaining pillars and avoid duplicates.

    No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset or packages are absent.
    """
    if _otel_state["setup_in_progress"]:
        # Prevent re-entrancy if called during another setup attempt.
        return

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    service_name = os.environ.get("OTEL_SERVICE_NAME", "m8flow-backend")

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("OpenTelemetry packages not available; skipping OTEL setup")
        return

    resource = Resource({SERVICE_NAME: service_name})

    configured: list[str] = []
    _otel_state["setup_in_progress"] = True
    try:
        # --- Traces ---
        if not _otel_state["traces"]:
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
            trace.set_tracer_provider(tracer_provider)
            _otel_state["traces"] = True
            configured.append("traces")

        # --- Logs ---
        if not _otel_state["logs"]:
            # Public SDK log path (>=1.22) with narrow fallback to private path.
            try:
                from opentelemetry.sdk.logs import LoggerProvider as OtelLoggerProvider
                from opentelemetry.sdk.logs import LoggingHandler as OtelLoggingHandler
                from opentelemetry.sdk.logs.export import BatchLogRecordProcessor
            except ImportError:  # pragma: no cover
                from opentelemetry.sdk._logs import LoggerProvider as OtelLoggerProvider
                from opentelemetry.sdk._logs import LoggingHandler as OtelLoggingHandler
                from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

            # Public exporter path with narrow fallback.
            try:
                from opentelemetry.exporter.otlp.proto.grpc.log_exporter import OTLPLogExporter
            except ImportError:  # pragma: no cover
                from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

            # Provider registration API is currently in opentelemetry._logs.
            try:
                from opentelemetry._logs import set_logger_provider
            except ImportError as e:  # pragma: no cover
                raise ImportError("OpenTelemetry log provider API not available") from e

            log_provider = OtelLoggerProvider(resource=resource)
            log_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint)))
            set_logger_provider(log_provider)

            global _otel_logging_handler
            if _otel_logging_handler is None:
                _otel_logging_handler = OtelLoggingHandler(level=logging.NOTSET, logger_provider=log_provider)
                # Mark handler so we can detect duplicates even if type matches other handlers.
                setattr(_otel_logging_handler, "_m8flow_otel_handler", True)

            root = logging.getLogger()
            if not _root_logger_has_handler(type(_otel_logging_handler), marker_attr="_m8flow_otel_handler"):
                root.addHandler(_otel_logging_handler)

            _otel_state["logs"] = True
            configured.append("logs")

        # --- Metrics ---
        if not _otel_state["metrics"]:
            meter_provider = MeterProvider(
                resource=resource,
                metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint))],
            )
            metrics.set_meter_provider(meter_provider)
            _otel_state["metrics"] = True
            configured.append("metrics")

        # --- Instrumentation ---
        if not _otel_state["instrumentation"]:
            FlaskInstrumentor().instrument_app(app)
            SQLAlchemyInstrumentor().instrument()
            # set_logging_format=False preserves the existing TenantAwareFormatter output
            LoggingInstrumentor().instrument(set_logging_format=False)
            _otel_state["instrumentation"] = True
            configured.append("instrumentation")

    except Exception:
        # Keep partial success markers; caller may retry to complete remaining pillars.
        logger.exception(
            "OpenTelemetry setup failed (service=%s, endpoint=%s, state=%s)",
            service_name,
            endpoint,
            {k: v for k, v in _otel_state.items() if k != "setup_in_progress"},
        )
        return
    finally:
        _otel_state["setup_in_progress"] = False

    if configured:
        logger.info(
            "OpenTelemetry configured (service=%s, endpoint=%s, configured=%s)",
            service_name,
            endpoint,
            ",".join(configured),
        )
