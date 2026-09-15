from __future__ import annotations

import json
import logging

from m8flow_backend.observability.logging_json import JsonLogFormatter, OtelTraceFilter, build_formatter


def _make_record(level=logging.INFO, msg="hello world", exc_info=None) -> logging.LogRecord:
    return logging.LogRecord(
        name="m8flow_backend.test",
        level=level,
        pathname=__file__,
        lineno=42,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )


def test_json_formatter_produces_valid_json_with_core_fields():
    record = _make_record()
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "m8flow_backend.test"
    assert payload["service"] == "m8flow-backend"
    assert "timestamp" in payload


def test_json_formatter_includes_tenant_and_request_id_when_present():
    record = _make_record()
    record.m8flow_tenant_id = "tenant-a"
    record.m8flow_request_id = "req-123"
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["tenant_id"] == "tenant-a"
    assert payload["request_id"] == "req-123"


def test_json_formatter_omits_unset_context_placeholders():
    record = _make_record()
    record.m8flow_tenant_id = "-"
    record.m8flow_request_id = "-"
    record.otel_trace_id = "-"
    record.otel_span_id = "-"
    payload = json.loads(JsonLogFormatter().format(record))
    assert "tenant_id" not in payload
    assert "request_id" not in payload
    assert "trace_id" not in payload
    assert "span_id" not in payload


def test_json_formatter_captures_exception_details():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _make_record(level=logging.ERROR, msg="failed", exc_info=sys.exc_info())
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["exception"]["type"] == "ValueError"
    assert payload["exception"]["message"] == "boom"
    assert "Traceback" in payload["exception"]["stacktrace"]


def test_json_formatter_nests_unknown_extra_fields():
    record = _make_record()
    record.custom_field = "custom-value"
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["extra"]["custom_field"] == "custom-value"


def test_json_formatter_promotes_error_taxonomy_fields():
    record = _make_record(level=logging.ERROR, msg="failed")
    record.error_code = "permission_denied"
    record.http_status = 403
    record.http_method = "GET"
    record.http_path = "/v1.0/tasks"
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["error_code"] == "permission_denied"
    assert payload["http_status"] == 403
    assert payload["error_kind"] == "client"
    assert payload["http_method"] == "GET"
    assert payload["http_path"] == "/v1.0/tasks"
    assert "error_code" not in payload.get("extra", {})
    assert "http_status" not in payload.get("extra", {})


def test_json_formatter_promotes_duration_ms():
    record = _make_record(msg="request completed")
    record.duration_ms = 12.5
    record.http_status = 200
    record.http_method = "GET"
    record.http_path = "/v1.0/tasks"
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["duration_ms"] == 12.5
    assert "duration_ms" not in payload.get("extra", {})


def test_json_formatter_promotes_sql_timing_fields():
    record = _make_record(msg="sql query slow")
    record.duration_ms = 180.25
    record.sql_query_count = 7
    record.sql_duration_ms = 42.5
    record.sql_pool_checkedout = 2
    record.sql_pool_size = 5
    record.sql_operation = "SELECT"
    record.sql_statement = "SELECT id FROM process_instance"
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["sql_query_count"] == 7
    assert payload["sql_duration_ms"] == 42.5
    assert payload["sql_pool_checkedout"] == 2
    assert payload["sql_pool_size"] == 5
    assert payload["sql_operation"] == "SELECT"
    assert payload["sql_statement"] == "SELECT id FROM process_instance"
    extra = payload.get("extra", {})
    assert "sql_query_count" not in extra
    assert "sql_statement" not in extra


def test_json_formatter_promotes_process_instance_duration():
    record = _make_record(msg="process instance completed")
    record.duration_seconds = 42.0
    record.process_instance_id = 17
    record.process_instance_status = "complete"
    record.process_model_identifier = "invoices/approval"
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["duration_seconds"] == 42.0
    assert payload["process_instance_id"] == 17
    assert payload["process_instance_status"] == "complete"
    assert payload["process_model_identifier"] == "invoices/approval"
    extra = payload.get("extra", {})
    assert "duration_seconds" not in extra
    assert "process_instance_id" not in extra
    assert "process_model_identifier" not in extra


def test_json_formatter_error_kind_is_server_for_5xx():
    record = _make_record(level=logging.ERROR, msg="failed")
    record.error_code = "internal_error"
    record.m8flow_status_code = 500
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["http_status"] == 500
    assert payload["error_kind"] == "server"
    assert "m8flow_status_code" not in payload.get("extra", {})


def test_otel_trace_filter_is_a_noop_without_an_active_span():
    record = _make_record()
    assert OtelTraceFilter().filter(record) is True
    assert record.otel_trace_id == "-"
    assert record.otel_span_id == "-"


def test_build_formatter_selects_text_via_env_var(monkeypatch):
    monkeypatch.setenv("M8FLOW_LOG_FORMAT", "text")
    formatter = build_formatter()
    assert isinstance(formatter, logging.Formatter)
    assert not isinstance(formatter, JsonLogFormatter)


def test_build_formatter_defaults_to_json(monkeypatch):
    monkeypatch.delenv("M8FLOW_LOG_FORMAT", raising=False)
    assert isinstance(build_formatter(), JsonLogFormatter)
