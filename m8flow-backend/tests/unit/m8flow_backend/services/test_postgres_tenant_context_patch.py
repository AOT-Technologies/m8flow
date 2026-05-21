from flask import Flask
from flask import g

from m8flow_backend.services import tenant_scoping_patch  # noqa: E402
from m8flow_backend.tenancy import reset_context_tenant_id  # noqa: E402
from m8flow_backend.tenancy import set_context_tenant_id  # noqa: E402


class FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeCursor:
    def __init__(self, owner: "FakeConnection") -> None:
        self.owner = owner

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.owner.calls.append((sql, params))

    def close(self) -> None:
        self.owner.close_calls += 1


class FakeConnection:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = FakeDialect(dialect_name)
        self.calls: list[tuple[str, tuple | None]] = []
        self.connection = self
        self.close_calls = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_postgres_sets_tenant_context_from_request() -> None:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    connection = FakeConnection("postgresql")

    with app.test_request_context("/"):
        g.m8flow_tenant_id = "tenant-a"
        tenant_scoping_patch._set_postgres_tenant_context(None, None, connection)

    assert connection.calls == [("SET LOCAL app.current_tenant = %s", ("tenant-a",))]
    assert connection.close_calls == 1


def test_postgres_sets_tenant_context_from_background() -> None:
    connection = FakeConnection("postgresql")
    token = set_context_tenant_id("tenant-b")
    try:
        tenant_scoping_patch._set_postgres_tenant_context(None, None, connection)
    finally:
        reset_context_tenant_id(token)

    assert connection.calls == [("SET LOCAL app.current_tenant = %s", ("tenant-b",))]
    assert connection.close_calls == 1


def test_postgres_missing_tenant_does_nothing() -> None:
    connection = FakeConnection("postgresql")

    tenant_scoping_patch._set_postgres_tenant_context(None, None, connection)

    assert connection.calls == []
    assert connection.close_calls == 0


def test_non_postgres_does_nothing() -> None:
    connection = FakeConnection("sqlite")

    tenant_scoping_patch._set_postgres_tenant_context(None, None, connection)

    assert connection.calls == []
    assert connection.close_calls == 0
