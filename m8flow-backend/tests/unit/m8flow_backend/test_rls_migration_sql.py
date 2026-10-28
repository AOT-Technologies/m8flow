"""RLS DDL in these migrations runs through sa.DDL; pin that it emits exactly what sa.text did.

Runs each migration's RLS helper in Alembic offline (--sql) mode for PostgreSQL, once as
written (sa.DDL) and once with sa.DDL swapped for sa.text (the pre-change form), and
requires identical SQL. Online mode compiles the same DDL element against the live dialect.
"""

from __future__ import annotations

import importlib.util
import io
import types
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

_VERSIONS = Path(__file__).resolve().parents[3] / "migrations" / "versions"

# migration file -> how to call its RLS helper
_CASES = {
    "2c7e9a41d5f3_add_nats_event_audit.py": lambda m: m._enable_rls(),
    "7d4b1e9c3a20_nats_api_keys_full_schema.py": lambda m: m._enable_rls("m8flow_nats_api_key"),
    "b7e1c2d3f4a5_add_process_instance_error.py": lambda m: m._enable_rls(),
    "b2c3d4e5f6a7_upgrade_core_0_2_0_compatibility.py": lambda m: m._ensure_tenant_rls("work_item"),
}


def _load(file_name: str, *, ddl_as_text: bool):
    spec = importlib.util.spec_from_file_location(f"rls_{file_name[:12]}_{ddl_as_text}", _VERSIONS / file_name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._is_postgres = lambda: True
    module._table_exists = lambda _name: True
    module._bind = lambda: types.SimpleNamespace(dialect=postgresql.dialect())
    if ddl_as_text:
        module.sa = types.SimpleNamespace(**{**vars(sa), "DDL": sa.text})
    return module


def _offline_sql(module, call) -> str:
    buffer = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})
    with Operations.context(context):
        call(module)
    return buffer.getvalue()


@pytest.mark.parametrize("file_name", sorted(_CASES))
def test_rls_ddl_matches_the_previous_text_form_offline(file_name):
    call = _CASES[file_name]
    as_ddl = _offline_sql(_load(file_name, ddl_as_text=False), call)
    as_text = _offline_sql(_load(file_name, ddl_as_text=True), call)
    assert as_ddl == as_text
    assert as_ddl.count("ENABLE ROW LEVEL SECURITY") == 1
    assert as_ddl.count("CREATE POLICY") == 2
    assert as_ddl.count("DROP POLICY IF EXISTS") == 2


def test_ddl_compiles_to_the_literal_statement_online():
    statement = "ALTER TABLE t ENABLE ROW LEVEL SECURITY"
    assert str(sa.DDL(statement).compile(dialect=postgresql.dialect())) == statement
