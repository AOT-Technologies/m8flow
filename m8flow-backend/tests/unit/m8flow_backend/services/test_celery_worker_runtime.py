from __future__ import annotations

from m8flow_backend.services.celery_worker_runtime import cleanup_scoped_session
from m8flow_backend.services.celery_worker_runtime import reset_engine_for_worker_process
from m8flow_backend.services.celery_worker_runtime import tenant_id_for_process_instance


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class FakeConnection:
    def __init__(self, value):
        self.value = value
        self.calls: list[tuple[str, dict[str, int]]] = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return FakeResult(self.value)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeEngine:
    def __init__(self, value):
        self.connection = FakeConnection(value)

    def connect(self):
        return self.connection


class FakeScopedSession:
    def __init__(self, *, fail_rollback: bool = False, fail_remove: bool = False) -> None:
        self.fail_rollback = fail_rollback
        self.fail_remove = fail_remove
        self.calls: list[str] = []

    def rollback(self) -> None:
        self.calls.append("rollback")
        if self.fail_rollback:
            raise RuntimeError("rollback failed")

    def remove(self) -> None:
        self.calls.append("remove")
        if self.fail_remove:
            raise RuntimeError("remove failed")


class FakeEngineWithDispose:
    def __init__(self, *, fail_dispose: bool = False) -> None:
        self.fail_dispose = fail_dispose
        self.dispose_calls = 0

    def dispose(self) -> None:
        self.dispose_calls += 1
        if self.fail_dispose:
            raise RuntimeError("dispose failed")


def test_tenant_id_for_process_instance_uses_engine_connection() -> None:
    engine = FakeEngine("tenant-a")

    tenant_id = tenant_id_for_process_instance(engine, 42)

    assert tenant_id == "tenant-a"
    assert engine.connection.calls == [
        ("SELECT m8f_tenant_id FROM process_instance WHERE id = :process_instance_id", {"process_instance_id": 42})
    ]


def test_tenant_id_for_process_instance_returns_none_for_missing_value() -> None:
    engine = FakeEngine(None)

    tenant_id = tenant_id_for_process_instance(engine, 42)

    assert tenant_id is None


def test_cleanup_scoped_session_rolls_back_and_removes() -> None:
    session = FakeScopedSession()

    cleanup_scoped_session(session)

    assert session.calls == ["rollback", "remove"]


def test_cleanup_scoped_session_still_removes_after_rollback_failure() -> None:
    session = FakeScopedSession(fail_rollback=True)

    cleanup_scoped_session(session)

    assert session.calls == ["rollback", "remove"]


def test_cleanup_scoped_session_swallows_remove_failure() -> None:
    session = FakeScopedSession(fail_remove=True)

    cleanup_scoped_session(session)

    assert session.calls == ["rollback", "remove"]


def test_reset_engine_for_worker_process_cleans_session_and_disposes_engine() -> None:
    session = FakeScopedSession()
    engine = FakeEngineWithDispose()

    reset_engine_for_worker_process(engine, session)

    assert session.calls == ["rollback", "remove"]
    assert engine.dispose_calls == 1


def test_reset_engine_for_worker_process_swallows_dispose_failure() -> None:
    session = FakeScopedSession()
    engine = FakeEngineWithDispose(fail_dispose=True)

    reset_engine_for_worker_process(engine, session)

    assert session.calls == ["rollback", "remove"]
    assert engine.dispose_calls == 1
