from __future__ import annotations

import logging

from m8flow_backend.observability.request_context import REQUEST_ID_HEADER


def test_request_id_is_generated_and_echoed(client):
    response = client.get("/v1.0/status")
    assert response.status_code == 200
    assert response.headers.get(REQUEST_ID_HEADER)


def test_inbound_request_id_is_preserved(client):
    response = client.get("/v1.0/status", headers={REQUEST_ID_HEADER: "req-fixed-123"})
    assert response.headers.get(REQUEST_ID_HEADER) == "req-fixed-123"


def test_each_request_gets_a_distinct_request_id(client):
    first = client.get("/v1.0/status").headers.get(REQUEST_ID_HEADER)
    second = client.get("/v1.0/status").headers.get(REQUEST_ID_HEADER)
    assert first and second and first != second


def test_request_completed_log_includes_duration_ms(client, caplog):
    caplog.set_level(logging.INFO, logger="m8flow_backend.observability.request_context")
    client.get("/v1.0/onboarding")
    records = [
        record
        for record in caplog.records
        if record.name == "m8flow_backend.observability.request_context"
        and record.getMessage() == "request completed"
    ]
    assert records
    assert isinstance(records[-1].duration_ms, float)
    assert records[-1].duration_ms >= 0
    assert records[-1].http_method == "GET"
    assert records[-1].http_path == "/v1.0/onboarding"
    assert records[-1].sql_query_count >= 0
    assert records[-1].sql_duration_ms >= 0


def test_status_probe_does_not_emit_request_completed_log(client, caplog):
    caplog.set_level(logging.INFO, logger="m8flow_backend.observability.request_context")
    client.get("/v1.0/status")
    assert not [
        record
        for record in caplog.records
        if record.getMessage() == "request completed"
    ]
