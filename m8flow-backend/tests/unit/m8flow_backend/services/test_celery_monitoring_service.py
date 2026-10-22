"""Celery monitoring service: normalization against a real capture, redaction, errors, cache.

``celery_inspect.json`` was recorded from a Celery 5.6.3 worker (concurrency 1) holding
one running task, one waiting task whose kwargs carry a fake ``api_key``, and one task
revoked while still waiting.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from kombu.exceptions import OperationalError

from m8flow_backend.errors import ApiError
from m8flow_backend.services import celery_monitoring_service as module
from m8flow_backend.services.celery_monitoring_service import CeleryMonitoringService as Service

WORKER = "fixture-worker@m8flow"
RUNNING = "bd530db3-7a0e-4a31-8772-bd329065bc4e"
WAITING = "bf2ded3d-52eb-4fde-8f38-6643ce2be63a"
REVOKED = "33fc657d-28a5-4fde-bf59-5b6045f15031"


@pytest.fixture
def snapshot() -> dict:
    raw = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "celery_inspect.json").read_text())
    return {
        **raw,
        "conf": {WORKER: {"broker_url": "redis://:s3cret-pass@redis:6379/0", "worker_concurrency": 1, "secret_key": "x"}},
        "transport": "redis",
        "broker": {"queues": [{"name": "m8flow-fixture", "messages": 1, "consumers": [WORKER]}], "unacked": 2},
        "captured_at": "2026-10-21T10:15:00+00:00",
    }


@pytest.fixture(autouse=True)
def clear_cache():
    module._cache.update(at=0.0, snapshot=None)
    yield
    module._cache.update(at=0.0, snapshot=None)


class TestNormalizeOverview:
    def test_counts_from_a_real_capture(self, snapshot):
        assert Service.normalize_overview(snapshot) == {
            "workersOnline": 1,
            "concurrency": 1,
            "tasksRunning": 1,
            "tasksReserved": 2,
            "tasksScheduled": 0,
            "tasksProcessed": 1,  # stats.total counts a task once the worker starts it
            "queues": [{"name": "m8flow-fixture", "messages": 1, "consumers": [WORKER]}],
            "unacked": 2,
            "transport": "redis",
            "capturedAt": "2026-10-21T10:15:00+00:00",
        }

    def test_no_workers_is_all_zeros_not_an_error(self):
        overview = Service.normalize_overview({"ping": {}})
        assert overview["workersOnline"] == 0
        assert overview["tasksRunning"] == overview["tasksProcessed"] == 0

    def test_overview_adds_history_counts_offline_workers_and_flags(self, snapshot, monkeypatch):
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_MONITORING_ENABLED", "true")
        monkeypatch.setattr(module, "_collect", lambda: snapshot)
        from m8flow_backend.services.celery_task_history_service import CeleryTaskHistoryService

        monkeypatch.setattr(CeleryTaskHistoryService, "recent_workers", staticmethod(lambda hours: {WORKER: "t", "celery@gone": "t"}))
        monkeypatch.setattr(CeleryTaskHistoryService, "summary", staticmethod(lambda hours: {"SUCCESS": 9, "FAILURE": 2}))
        overview = Service.overview()
        assert overview["workersOffline"] == 1
        assert overview["history"] == {"windowHours": 24, "succeeded": 9, "failed": 2, "retried": 0, "revoked": 0}
        assert overview["historyEnabled"] is True and overview["controlEnabled"] is True

    def test_a_broken_history_table_does_not_blank_the_page(self, snapshot, monkeypatch):
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_MONITORING_ENABLED", "true")
        monkeypatch.setattr(module, "_collect", lambda: snapshot)
        from m8flow_backend.services.celery_task_history_service import CeleryTaskHistoryService

        def missing_table(hours):
            raise RuntimeError("no such table: m8flow_celery_task")

        monkeypatch.setattr(CeleryTaskHistoryService, "summary", staticmethod(missing_table))
        monkeypatch.setattr(CeleryTaskHistoryService, "recent_workers", staticmethod(missing_table))
        overview = Service.overview()
        assert overview["workersOnline"] == 1
        assert overview["history"]["succeeded"] == 0


class TestNormalizeWorkers:
    def test_fields_picked_from_stats_queues_registry_and_rusage(self, snapshot):
        [worker] = Service.normalize_workers(snapshot)
        assert worker["name"] == WORKER and worker["online"] is True
        assert worker["pool"] == "prefork"
        assert worker["concurrency"] == 1 and worker["processes"] == 1
        assert worker["prefetchCount"] == 2
        assert worker["queues"] == ["m8flow-fixture"]
        assert worker["registeredTasks"] == ["fixture.slow"]
        assert (worker["running"], worker["reserved"], worker["scheduled"]) == (1, 2, 0)
        assert set(worker["system"]) <= {"utime", "stime", "maxrss", "minflt", "majflt", "nvcsw", "nivcsw"}
        assert "maxrss" in worker["system"]

    def test_broker_connection_details_never_leave(self, snapshot):
        """stats.broker names the broker host, port and user; a password could sit there too."""
        snapshot = copy.deepcopy(snapshot)
        snapshot["stats"][WORKER]["broker"]["password"] = "hunter2"
        rendered = json.dumps(Service.normalize_workers(snapshot))
        assert "hunter2" not in rendered
        assert "6848" not in rendered

    def test_config_masks_url_passwords_and_secret_keys(self, snapshot):
        [worker] = Service.normalize_workers(snapshot)
        conf = {row["key"]: row["value"] for row in worker["conf"]}
        assert conf["broker_url"] == "redis://:***@redis:6379/0"
        assert conf["secret_key"] == "[redacted]"
        assert conf["worker_concurrency"] == "1"
        assert "s3cret-pass" not in json.dumps(worker)

    def test_workers_seen_in_history_but_silent_are_listed_offline(self, snapshot):
        rows = Service.normalize_workers(snapshot, {WORKER: "2026-10-21T10:00:00+00:00", "celery@gone": "2026-10-20T09:00:00+00:00"})
        assert [(row["name"], row["online"]) for row in rows] == [(WORKER, True), ("celery@gone", False)]
        assert rows[1] == {"name": "celery@gone", "online": False, "lastSeenAt": "2026-10-20T09:00:00+00:00"}


class TestNormalizeTasks:
    def test_lists_running_and_waiting_tasks(self, snapshot):
        tasks = Service.normalize_tasks(snapshot)
        [running] = tasks["active"]
        assert running["id"] == RUNNING
        assert running["name"] == "fixture.slow"
        assert running["worker"] == WORKER
        assert running["queue"] == "m8flow-fixture"
        assert running["startedAt"].endswith("+00:00")
        assert running["args"] == "[30]"
        assert running["kwargs"] == '{"process_instance_id": 42}'
        assert {t["id"] for t in tasks["reserved"]} == {WAITING, REVOKED}

    def test_secrets_in_task_arguments_are_redacted(self, snapshot):
        """reserved() ignores safe=True and returns raw kwargs, as the capture shows."""
        rendered = json.dumps(Service.normalize_tasks(snapshot))
        assert "not-a-real-key" not in rendered
        waiting = next(t for t in Service.normalize_tasks(snapshot)["reserved"] if t["id"] == WAITING)
        assert json.loads(waiting["kwargs"]) == {"process_instance_id": 43, "api_key": "[redacted]"}

    def test_revoked_task_still_waiting_is_flagged(self, snapshot):
        tasks = Service.normalize_tasks(snapshot)
        assert tasks["revoked"] == [REVOKED]
        flags = {t["id"]: t["revoked"] for t in tasks["reserved"]}
        assert flags == {WAITING: False, REVOKED: True}

    def test_scheduled_entries_unwrap_their_request(self, snapshot):
        """scheduled() wraps each request as {eta, priority, request} (celery/worker/control.py)."""
        snapshot = copy.deepcopy(snapshot)
        request = snapshot["reserved"][WORKER][0]
        snapshot["scheduled"] = {WORKER: [{"eta": "2026-10-21T10:25:00+00:00", "priority": 6, "request": request}]}
        [scheduled] = Service.normalize_tasks(snapshot)["scheduled"]
        assert scheduled["id"] == request["id"]
        assert scheduled["eta"] == "2026-10-21T10:25:00+00:00"
        assert "not-a-real-key" not in scheduled["kwargs"]

    def test_long_arguments_are_cut_after_redaction(self):
        request = {"id": "t1", "name": "n", "args": ["x" * 2000], "kwargs": {}}
        [task] = Service.normalize_tasks({"active": {WORKER: [request]}})["active"]
        assert len(task["args"]) == module.ARGS_PREVIEW_MAX_CHARS + 1
        assert task["args"].endswith("…")


class TestErrors:
    def test_disabled_is_a_503(self, monkeypatch):
        monkeypatch.setattr(module, "celery_monitoring_enabled", lambda: False)
        with pytest.raises(ApiError) as exc:
            Service.overview()
        assert exc.value.status_code == 503
        assert exc.value.error_code == "celery_monitoring_disabled"

    def test_unreachable_broker_is_a_503_without_internals(self, monkeypatch):
        monkeypatch.setattr(module, "celery_monitoring_enabled", lambda: True)

        class DeadConnection:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def ensure_connection(self, **_kwargs):
                raise OperationalError("Error 111 connecting to redis-internal:6379. Connection refused.")

        from m8flow_backend.scheduler import celery_app

        monkeypatch.setattr(celery_app, "connection_for_write", lambda: DeadConnection())
        with pytest.raises(ApiError) as exc:
            Service.overview()
        assert exc.value.status_code == 503
        assert exc.value.error_code == "celery_monitoring_unavailable"
        assert "redis-internal" not in exc.value.message


class TestBrokerCounts:
    class Channel:
        client = type("Client", (), {"llen": staticmethod(lambda name: 3), "hlen": staticmethod(lambda key: 5)})()
        unacked_key = "unacked"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def test_counted_on_a_fresh_channel_not_the_reply_channel(self, snapshot):
        """Live regression: an LLEN on the default channel, which just consumed the inspect
        replies with BRPOP, made kombu's close read the wrong reply and raise TypeError."""
        channel = self.Channel

        class Conn:
            @property
            def default_channel(self):
                raise AssertionError("queue depth must not use the inspect reply channel")

            def channel(self):
                return channel()

        assert module._broker_counts(Conn(), snapshot, "celery") == {
            "queues": [{"name": "m8flow-fixture", "messages": 3, "consumers": [WORKER]}],
            "unacked": 5,
        }

    def test_non_redis_broker_reports_unknown_depth(self, snapshot):
        assert module._broker_counts(object(), {**snapshot, "transport": "amqp"}, "celery") == {
            "queues": [{"name": "m8flow-fixture", "messages": None, "consumers": [WORKER]}],
            "unacked": None,
        }


class TestCache:
    def test_one_broadcast_round_serves_every_endpoint_within_the_window(self, monkeypatch, snapshot):
        monkeypatch.setattr(module, "celery_monitoring_enabled", lambda: True)
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_TASK_HISTORY_ENABLED", "false")
        calls = []
        monkeypatch.setattr(module, "_collect", lambda: calls.append(1) or snapshot)
        Service.overview()
        Service.workers()
        Service.tasks()
        Service.broker()
        assert len(calls) == 1

    def test_expired_snapshot_is_collected_again(self, monkeypatch, snapshot):
        monkeypatch.setattr(module, "celery_monitoring_enabled", lambda: True)
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_TASK_HISTORY_ENABLED", "false")
        calls = []
        monkeypatch.setattr(module, "_collect", lambda: calls.append(1) or snapshot)
        Service.overview()
        module._cache["at"] -= module.CACHE_SECONDS + 1
        Service.overview()
        assert len(calls) == 2

    def test_a_failure_is_not_cached(self, monkeypatch, snapshot):
        monkeypatch.setattr(module, "celery_monitoring_enabled", lambda: True)
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_TASK_HISTORY_ENABLED", "false")
        outcomes = iter([ApiError(error_code="celery_monitoring_unavailable", message="down", status_code=503), snapshot])

        def collect():
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(module, "_collect", collect)
        with pytest.raises(ApiError):
            Service.overview()
        assert Service.overview()["workersOnline"] == 1
