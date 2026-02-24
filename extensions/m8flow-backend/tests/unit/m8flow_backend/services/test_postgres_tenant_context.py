# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_postgres_tenant_context.py
import os
import sys
from pathlib import Path

import pytest
from flask import Flask
from flask import g

extension_root = Path(__file__).resolve().parents[1]
repo_root = extension_root.parents[1]
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.services import tenant_scoping_patch  # noqa: E402
from m8flow_backend.tenancy import reset_context_tenant_id  # noqa: E402
from m8flow_backend.tenancy import set_context_tenant_id  # noqa: E402


class FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeConnection:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = FakeDialect(dialect_name)
        self.calls: list[tuple[str, tuple | None]] = []

    def exec_driver_sql(self, sql: str, params: tuple | None = None) -> None:
        self.calls.append((sql, params))


def test_postgres_sets_tenant_context_from_request() -> None:
    os.environ.pop("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", None)
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    connection = FakeConnection("postgresql")

    with app.test_request_context("/"):
        g.m8flow_tenant_id = "tenant-a"
        tenant_scoping_patch._set_postgres_tenant_context(None, None, connection)

    assert connection.calls == [("SET LOCAL app.current_tenant = %s", ("tenant-a",))]


def test_postgres_sets_tenant_context_from_background() -> None:
    os.environ.pop("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", None)
    connection = FakeConnection("postgresql")
    token = set_context_tenant_id("tenant-b")
    try:
        tenant_scoping_patch._set_postgres_tenant_context(None, None, connection)
    finally:
        reset_context_tenant_id(token)

    assert connection.calls == [("SET LOCAL app.current_tenant = %s", ("tenant-b",))]


def test_postgres_missing_tenant_defaults_to_default_when_allowed(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "true")
    connection = FakeConnection("postgresql")

    tenant_scoping_patch._set_postgres_tenant_context(None, None, connection)

    assert connection.calls == [("SET LOCAL app.current_tenant = %s", ("default",))]


def test_postgres_missing_tenant_uses_default() -> None:
    """When no request/context tenant (e.g. background job), default tenant is used."""
    os.environ.pop("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", None)
    default_id = os.environ.get("M8FLOW_DEFAULT_TENANT_ID", "default")
    connection = FakeConnection("postgresql")

    tenant_scoping_patch._set_postgres_tenant_context(None, None, connection)

    assert connection.calls == [("SET LOCAL app.current_tenant = %s", (default_id,))]


def test_non_postgres_does_nothing() -> None:
    os.environ.pop("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", None)
    connection = FakeConnection("sqlite")

    tenant_scoping_patch._set_postgres_tenant_context(None, None, connection)

    assert connection.calls == []
