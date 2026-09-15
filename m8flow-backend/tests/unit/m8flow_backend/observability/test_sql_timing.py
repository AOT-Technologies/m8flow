from __future__ import annotations

import logging

from sqlalchemy import text

from m8flow_backend.db import get_engine, reset_engine
from m8flow_backend.observability.sql_timing import statement_operation, statement_preview


def test_statement_preview_compacts_and_truncates():
    assert statement_preview("select   1") == "select 1"
    long_sql = "SELECT " + ("x" * 400)
    preview = statement_preview(long_sql, limit=20)
    assert preview.endswith("…")
    assert len(preview) == 20


def test_statement_operation_reads_leading_keyword():
    assert statement_operation("  select id from process_instance") == "SELECT"
    assert statement_operation("") == ""


def test_engine_listeners_time_statements(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("M8FLOW_BACKEND_DATABASE_URI", f"sqlite:///{tmp_path / 'sql-timing.db'}")
    monkeypatch.setenv("M8FLOW_SQL_SLOW_MS", "0")
    reset_engine()
    try:
        engine = get_engine()
        caplog.set_level(logging.INFO, logger="m8flow_backend.observability.sql_timing")
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        slow = [record for record in caplog.records if record.getMessage() == "sql query slow"]
        assert slow
        assert slow[-1].sql_operation == "SELECT"
        assert "SELECT 1" in slow[-1].sql_statement
        assert float(slow[-1].duration_ms) >= 0
    finally:
        reset_engine()


def test_sql_totals_accumulate_on_flask_g(app):
    from flask import g
    from sqlalchemy import text

    from m8flow_backend.db import get_engine

    with app.test_request_context("/v1.0/onboarding"):
        g._m8flow_sql_query_count = 0
        g._m8flow_sql_duration_ms = 0.0
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        assert g._m8flow_sql_query_count >= 1
        assert g._m8flow_sql_duration_ms >= 0
