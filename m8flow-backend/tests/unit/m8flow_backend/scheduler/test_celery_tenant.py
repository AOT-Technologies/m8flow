from __future__ import annotations

from types import SimpleNamespace

from celery import Celery

from m8flow_backend.identity import ensure_tenant
from m8flow_backend.models.m8flow_tenant import TenantStatus
from m8flow_backend.scheduler import poll_due_jobs
from m8flow_backend.scheduler.celery_tenant import (
    TenantAwareCelery,
    bind_celery_task_tenant,
    clear_celery_task_tenant,
)
from m8flow_backend.auth.tenant_context import (
    TENANT_SELECTION_HEADER_NAME,
    get_context_tenant_id,
    reset_context_tenant_id,
    set_context_tenant_id,
)


def test_send_task_injects_header_from_context(monkeypatch):
    captured: dict[str, object] = {}

    def fake_send(self, name, args=None, kwargs=None, **options):
        captured["name"] = name
        captured["headers"] = options.get("headers")
        return "ok"

    monkeypatch.setattr(Celery, "send_task", fake_send)
    app = TenantAwareCelery("m8flow-test")
    token = set_context_tenant_id("tenant-a")
    try:
        result = app.send_task("demo.task")
    finally:
        reset_context_tenant_id(token)

    assert result == "ok"
    assert captured["name"] == "demo.task"
    assert captured["headers"][TENANT_SELECTION_HEADER_NAME] == "tenant-a"


def test_send_task_skips_header_when_tenant_missing(monkeypatch):
    captured: dict[str, object] = {}

    def fake_send(self, name, args=None, kwargs=None, **options):
        captured["headers"] = options.get("headers")
        return "ok"

    monkeypatch.setattr(Celery, "send_task", fake_send)
    app = TenantAwareCelery("m8flow-test")
    app.send_task("demo.task")
    assert captured["headers"] is None


def test_send_task_does_not_overwrite_existing_header(monkeypatch):
    captured: dict[str, object] = {}

    def fake_send(self, name, args=None, kwargs=None, **options):
        captured["headers"] = options.get("headers")
        return "ok"

    monkeypatch.setattr(Celery, "send_task", fake_send)
    app = TenantAwareCelery("m8flow-test")
    token = set_context_tenant_id("from-context")
    try:
        app.send_task("demo.task", headers={TENANT_SELECTION_HEADER_NAME: "already"})
    finally:
        reset_context_tenant_id(token)

    assert captured["headers"][TENANT_SELECTION_HEADER_NAME] == "already"


def test_prerun_restores_context_from_header_and_postrun_clears():
    task = SimpleNamespace(
        request=SimpleNamespace(headers={TENANT_SELECTION_HEADER_NAME: "t9"})
    )
    bind_celery_task_tenant(task_id="abc", task=task)
    try:
        assert get_context_tenant_id() == "t9"
    finally:
        clear_celery_task_tenant(task_id="abc")
    assert get_context_tenant_id() is None


def test_prerun_ignores_task_without_tenant_header():
    task = SimpleNamespace(request=SimpleNamespace(headers={}))
    bind_celery_task_tenant(task_id="none", task=task)
    try:
        assert get_context_tenant_id() is None
    finally:
        clear_celery_task_tenant(task_id="none")


def test_poll_due_jobs_runs_per_active_tenant_never_none(monkeypatch, db_session):
    ensure_tenant(db_session, tenant_id="t-b", slug="t-b")
    ensure_tenant(db_session, tenant_id="t-a", slug="t-a")
    inactive = ensure_tenant(db_session, tenant_id="t-dead", slug="t-dead")
    inactive.status = TenantStatus.INACTIVE
    db_session.commit()

    calls: list[tuple[str | None, str | None]] = []

    def fake_run_due(session, **kwargs):
        calls.append((kwargs.get("tenant_id"), get_context_tenant_id()))
        return 0

    monkeypatch.setattr("m8flow_backend.workflow.run_due", fake_run_due)
    processed = poll_due_jobs(limit=100, worker_id="test-worker")

    assert processed == 0
    assert calls == [("t-a", "t-a"), ("t-b", "t-b")]
    assert all(tenant_id is not None for tenant_id, _ in calls)


def test_poll_due_jobs_with_no_tenants_does_not_call_run_due(monkeypatch, db_session):
    called = []

    def fake_run_due(session, **kwargs):
        called.append(kwargs)
        return 1

    monkeypatch.setattr("m8flow_backend.workflow.run_due", fake_run_due)
    assert poll_due_jobs() == 0
    assert called == []


def test_poll_due_jobs_shares_remaining_limit_across_tenants(monkeypatch, db_session):
    ensure_tenant(db_session, tenant_id="t1", slug="t1")
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    ensure_tenant(db_session, tenant_id="t3", slug="t3")
    db_session.commit()

    seen_limits: list[int] = []

    def fake_run_due(session, **kwargs):
        seen_limits.append(kwargs["limit"])
        tenant_id = kwargs["tenant_id"]
        if tenant_id == "t1":
            return 80
        if tenant_id == "t2":
            return 20
        return 1

    monkeypatch.setattr("m8flow_backend.workflow.run_due", fake_run_due)
    assert poll_due_jobs(limit=100, worker_id="test-worker") == 100
    assert seen_limits == [100, 20]
