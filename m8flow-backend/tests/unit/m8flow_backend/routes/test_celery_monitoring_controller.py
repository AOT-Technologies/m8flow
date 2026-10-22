"""Celery monitoring controller, called directly with the YAML gate stubbed open.

Exercises the controller's own super-admin check, the history switch, the actor passed
to control actions, and error pass-through. The real super-admin-only YAML enforcement
is covered in test_celery_monitoring_permissions.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask, g

from m8flow_backend.errors import ApiError
from m8flow_backend.routes import celery_monitoring_controller as controller


@pytest.fixture
def app():
    return Flask(__name__)  # NOSONAR - unit test, no HTTP server or CSRF involved


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    monkeypatch.setattr("m8flow_backend.authorization.decorators.allow_uri", lambda *_a, **_k: True)
    monkeypatch.setattr(controller, "is_super_admin_request", lambda: bool(getattr(g, "_test_super_admin", False)))
    monkeypatch.setattr(controller, "celery_task_history_enabled", lambda: True)
    calls: dict[str, object] = {}

    class Monitoring:
        overview = staticmethod(lambda: {"workersOnline": 1})
        workers = staticmethod(lambda: {"results": []})
        tasks = staticmethod(lambda: {"active": [], "reserved": [], "scheduled": [], "revoked": []})
        broker = staticmethod(lambda: {"queues": [], "unacked": 0})
        registered_task_names = staticmethod(lambda: {"m8flow.idle", "m8flow.busy"})

    class History:
        list_tasks = staticmethod(lambda **kw: calls.setdefault("list_tasks", kw) and {"results": [], "pagination": {}})
        get_task = staticmethod(lambda task_id: {"taskId": task_id})
        task_types = staticmethod(lambda hours: [{"name": "m8flow.busy", "total": 3}])

    class Control:
        @staticmethod
        def revoke(task_id, **kw):
            calls["revoke"] = (task_id, kw)
            return {"ok": True}

        @staticmethod
        def rate_limit(name, rate, **kw):
            calls["rate_limit"] = (name, rate, kw)
            return {"ok": True}

        @staticmethod
        def time_limit(name, soft, hard, **kw):
            calls["time_limit"] = (name, soft, hard, kw)
            return {"ok": True}

        @staticmethod
        def worker_action(worker, body, **kw):
            calls["worker_action"] = (worker, body, kw)
            return {"ok": True}

    monkeypatch.setattr(controller, "CeleryMonitoringService", Monitoring)
    monkeypatch.setattr(controller, "CeleryTaskHistoryService", History)
    monkeypatch.setattr(controller, "CeleryControlService", Control)
    return SimpleNamespace(calls=calls, monitoring=Monitoring)


def _as(app, *, user=SimpleNamespace(username="root"), super_admin: bool = False, query: str = "", json=None):
    ctx = app.test_request_context(f"/?{query}", method="POST" if json is not None else "GET", json=json)
    ctx.push()
    if user is not None:
        g.user = user
    g._test_super_admin = super_admin
    return ctx


ENDPOINTS = [
    ("overview", lambda: controller.overview()),
    ("workers", lambda: controller.workers()),
    ("tasks", lambda: controller.tasks()),
    ("broker", lambda: controller.broker()),
    ("history", lambda: controller.history()),
    ("history_task", lambda: controller.history_task("t1")),
    ("task_types", lambda: controller.task_types()),
    ("control_revoke", lambda: controller.control_revoke()),
    ("control_rate_limit", lambda: controller.control_rate_limit()),
    ("control_time_limit", lambda: controller.control_time_limit()),
    ("control_worker", lambda: controller.control_worker("celery@w1")),
]
IDS = [name for name, _ in ENDPOINTS]


@pytest.mark.parametrize("name,call", ENDPOINTS, ids=IDS)
def test_401_without_a_user(app, name, call):
    ctx = _as(app, user=None)
    try:
        assert call().status_code == 401
    finally:
        ctx.pop()


@pytest.mark.parametrize("name,call", ENDPOINTS, ids=IDS)
def test_403_for_an_authenticated_non_super_admin(app, name, call):
    ctx = _as(app, super_admin=False)
    try:
        response = call()
        assert response.status_code == 403
        assert response.get_json()["error_code"] == "forbidden"
    finally:
        ctx.pop()


@pytest.mark.parametrize("name,call", ENDPOINTS, ids=IDS)
def test_200_for_a_super_admin(app, name, call):
    ctx = _as(app, super_admin=True, json={} if name.startswith("control") else None)
    try:
        assert call().status_code == 200
    finally:
        ctx.pop()


def test_history_filters_reach_the_service(app, stubs):
    ctx = _as(app, super_admin=True, query="state=FAILURE&name=m8flow.busy&worker=w1&search=42&windowHours=6&page=2&perPage=25")
    try:
        controller.history()
    finally:
        ctx.pop()
    assert stubs.calls["list_tasks"] == {
        "state": "FAILURE", "name": "m8flow.busy", "worker": "w1", "search": "42", "window_hours": 6, "page": 2, "per_page": 25,
        "sort": None, "order": None,
    }


def test_history_sort_reaches_the_service(app, stubs):
    ctx = _as(app, super_admin=True, query="sort=runtime&order=asc")
    try:
        controller.history()
    finally:
        ctx.pop()
    assert (stubs.calls["list_tasks"]["sort"], stubs.calls["list_tasks"]["order"]) == ("runtime", "asc")


def test_history_off_is_a_503(app, monkeypatch):
    monkeypatch.setattr(controller, "celery_task_history_enabled", lambda: False)
    ctx = _as(app, super_admin=True)
    try:
        response = controller.history()
        assert response.status_code == 503
        assert response.get_json()["error_code"] == "celery_history_disabled"
    finally:
        ctx.pop()


def test_task_types_include_registered_types_with_no_history(app):
    ctx = _as(app, super_admin=True)
    try:
        rows = controller.task_types().get_json()["results"]
    finally:
        ctx.pop()
    assert [(row["name"], row["total"]) for row in rows] == [("m8flow.busy", 3), ("m8flow.idle", 0)]


def test_control_actions_pass_the_body_and_the_acting_user(app, stubs):
    for call, body in [
        (controller.control_revoke, {"taskId": "t1", "terminate": True, "signal": "SIGKILL"}),
        (controller.control_rate_limit, {"taskName": "m8flow.busy", "rateLimit": "5/m"}),
        (controller.control_time_limit, {"taskName": "m8flow.busy", "softSeconds": 10, "hardSeconds": 20, "worker": "celery@w1"}),
        (lambda: controller.control_worker("celery@w1"), {"action": "pool_grow", "n": 1}),
    ]:
        ctx = _as(app, super_admin=True, json=body)
        try:
            assert call().status_code == 200
        finally:
            ctx.pop()
    assert stubs.calls["revoke"] == ("t1", {"terminate": True, "signal": "SIGKILL", "actor": "root"})
    assert stubs.calls["rate_limit"] == ("m8flow.busy", "5/m", {"actor": "root", "worker": None})
    assert stubs.calls["time_limit"] == ("m8flow.busy", 10, 20, {"actor": "root", "worker": "celery@w1"})
    assert stubs.calls["worker_action"] == ("celery@w1", {"action": "pool_grow", "n": 1}, {"actor": "root"})


def test_broker_down_reaches_the_client_as_a_503(app, stubs, monkeypatch):
    def down():
        raise ApiError(error_code="celery_monitoring_unavailable", message="The Celery broker is not reachable.", status_code=503)

    monkeypatch.setattr(stubs.monitoring, "overview", staticmethod(down))
    ctx = _as(app, super_admin=True)
    try:
        response = controller.overview()
        assert response.status_code == 503
        assert response.get_json()["error_code"] == "celery_monitoring_unavailable"
    finally:
        ctx.pop()
