"""Celery control actions: validation, the off switch, and what is sent to the workers."""

from __future__ import annotations

import pytest
from kombu.exceptions import OperationalError

from m8flow_backend.errors import ApiError
from m8flow_backend.scheduler import celery_app
from m8flow_backend.services import celery_control_service as module
from m8flow_backend.services.celery_control_service import CeleryControlService as Control

WORKER = "celery@worker-1"


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ensure_connection(self, **_kwargs):
        return self


@pytest.fixture
def sent(monkeypatch):
    """Record every control command instead of broadcasting it."""
    monkeypatch.setenv("M8FLOW_BACKEND_CELERY_CONTROL_ENABLED", "true")
    calls: list[tuple[str, tuple, dict]] = []

    def command(name):
        def send(*args, **kwargs):
            calls.append((name, args, kwargs))
            return [{WORKER: {"ok": f"{name} done"}}] if kwargs.get("reply") else None

        return send

    monkeypatch.setattr(celery_app, "connection_for_write", lambda: FakeConnection())
    for name in ("revoke", "rate_limit", "time_limit", "pool_grow", "pool_shrink", "autoscale",
                 "pool_restart", "add_consumer", "cancel_consumer", "shutdown"):
        monkeypatch.setattr(celery_app.control, name, command(name))
    return calls


def test_disabled_control_is_a_403(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_CELERY_CONTROL_ENABLED", "false")
    with pytest.raises(ApiError) as exc:
        Control.revoke("task-1", terminate=False, signal=None, actor="root")
    assert (exc.value.status_code, exc.value.error_code) == (403, "celery_control_disabled")


def test_revoke_and_terminate_broadcast_to_every_worker(sent):
    outcome = Control.revoke("task-1", terminate=True, signal="sigkill", actor="root")
    assert outcome == {"ok": True, "message": "revoke done", "results": [{"worker": WORKER, "ok": True, "message": "revoke done"}]}
    name, args, kwargs = sent[0]
    assert (name, args) == ("revoke", ("task-1",))
    assert kwargs["terminate"] is True and kwargs["signal"] == "SIGKILL" and kwargs["destination"] is None


def test_rate_limit_accepts_celery_forms_and_empty_removes_it(sent):
    Control.rate_limit("m8flow.task", "10/m", actor="root")
    Control.rate_limit("m8flow.task", "", actor="root")
    assert [call[1] for call in sent] == [("m8flow.task", "10/m"), ("m8flow.task", None)]


@pytest.mark.parametrize("bad", ["fast", "10/d", "-1", "10/mm"])
def test_rate_limit_rejects_anything_else(sent, bad):
    with pytest.raises(ApiError) as exc:
        Control.rate_limit("m8flow.task", bad, actor="root")
    assert exc.value.status_code == 400
    assert sent == []


def test_limits_go_to_every_worker_or_only_the_one_named(sent):
    """Flower's worker page sets limits for that worker only; the Task types tab for all."""
    Control.rate_limit("m8flow.task", "10/m", actor="root")
    Control.rate_limit("m8flow.task", "10/m", actor="root", worker="celery@w1")
    Control.time_limit("m8flow.task", 30, 60, actor="root", worker="celery@w1")
    assert [kwargs["destination"] for _name, _args, kwargs in sent] == [None, ["celery@w1"], ["celery@w1"]]
    with pytest.raises(ApiError) as exc:
        Control.rate_limit("m8flow.task", "10/m", actor="root", worker="celery@w1; rm -rf")
    assert exc.value.status_code == 400
    assert len(sent) == 3


def test_time_limit_validates_soft_against_hard(sent):
    Control.time_limit("m8flow.task", 30, 60, actor="root")
    assert sent[0][2]["soft"] == 30.0 and sent[0][2]["hard"] == 60.0
    with pytest.raises(ApiError):
        Control.time_limit("m8flow.task", 90, 60, actor="root")
    with pytest.raises(ApiError):
        Control.time_limit("m8flow.task", -1, None, actor="root")


def test_worker_actions_target_one_worker(sent):
    Control.worker_action(WORKER, {"action": "pool_grow", "n": 2}, actor="root")
    Control.worker_action(WORKER, {"action": "autoscale", "min": 2, "max": 6}, actor="root")
    Control.worker_action(WORKER, {"action": "add_consumer", "queue": "priority"}, actor="root")
    assert [(name, args, kwargs["destination"]) for name, args, kwargs in sent] == [
        ("pool_grow", (2,), [WORKER]),
        ("autoscale", (6, 2), [WORKER]),
        ("add_consumer", ("priority",), [WORKER]),
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"action": "pool_grow", "n": 0},
        {"action": "pool_grow", "n": 1.5},
        {"action": "autoscale", "min": 5, "max": 2},
        {"action": "add_consumer", "queue": "bad queue!"},
        {"action": "purge"},
    ],
)
def test_worker_actions_are_validated(sent, body):
    with pytest.raises(ApiError) as exc:
        Control.worker_action(WORKER, body, actor="root")
    assert exc.value.status_code == 400
    assert sent == []


def test_shutdown_does_not_wait_for_a_reply(sent):
    outcome = Control.worker_action(WORKER, {"action": "shutdown"}, actor="root")
    assert outcome["ok"] is True
    assert sent[0][2]["reply"] is False


def test_no_reply_and_error_replies_are_reported():
    assert module.summarize_replies([]) == {"ok": False, "message": "No worker answered.", "results": []}
    outcome = module.summarize_replies([{WORKER: {"error": "Pool restarts not enabled"}}])
    assert outcome["ok"] is False and outcome["message"] == "Pool restarts not enabled"


def test_unreachable_broker_is_a_503(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_CELERY_CONTROL_ENABLED", "true")

    class Dead(FakeConnection):
        def ensure_connection(self, **_kwargs):
            raise OperationalError("Error 111 connecting to redis-internal:6379")

    monkeypatch.setattr(celery_app, "connection_for_write", lambda: Dead())
    with pytest.raises(ApiError) as exc:
        Control.revoke("task-1", terminate=False, signal=None, actor="root")
    assert exc.value.status_code == 503
    assert "redis-internal" not in exc.value.message
