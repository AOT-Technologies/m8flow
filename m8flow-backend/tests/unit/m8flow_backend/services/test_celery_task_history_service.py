"""Celery task history: the worker-signal recorder and the read side, on SQLite.

The handlers are called directly with the shapes Celery passes them (a worker Request on
receive, the task's Context in the pool), so these tests need no broker or worker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from m8flow_backend.errors import ApiError
from m8flow_backend.models.celery_task import CeleryTaskModel
from m8flow_backend.services import celery_task_history_service as history
from m8flow_backend.services.celery_task_history_service import CeleryTaskHistoryService as Service

TASK = "m8flow_backend.scheduler.poll_due_task"
WORKER = "celery@worker-1"


@pytest.fixture(autouse=True)
def enabled(monkeypatch, db_engine):
    monkeypatch.setenv("M8FLOW_BACKEND_CELERY_TASK_HISTORY_ENABLED", "true")
    history._started.clear()


def _received(task_id: str, **kwargs):
    request = SimpleNamespace(
        id=task_id,
        name=kwargs.get("name", TASK),
        hostname=WORKER,
        delivery_info={"routing_key": "celery"},
        request_dict={"retries": 0, "x-m8flow-tenant-id": kwargs.get("tenant", "tenant-a")},
        args=kwargs.get("args", []),
        kwargs=kwargs.get("kwargs", {}),
        eta=None,
        expires=None,
        parent_id=None,
        root_id=task_id,
    )
    history.on_task_received(request=request)


def _task(name: str = TASK):
    return SimpleNamespace(name=name, request=SimpleNamespace(hostname=WORKER, delivery_info={"routing_key": "celery"}))


def _row(db_session, task_id: str) -> CeleryTaskModel:
    db_session.expire_all()
    return db_session.get(CeleryTaskModel, task_id)


class TestRecorder:
    def test_a_successful_task_goes_received_started_success(self, db_session):
        _received("t1", kwargs={"process_instance_id": 42})
        assert _row(db_session, "t1").state == "RECEIVED"

        history.on_task_prerun(task_id="t1", task=_task(), args=[], kwargs={"process_instance_id": 42})
        assert _row(db_session, "t1").state == "STARTED"

        history.on_task_postrun(task_id="t1", task=_task(), retval={"processed": 3}, state="SUCCESS")
        row = _row(db_session, "t1")
        assert row.state == "SUCCESS"
        assert row.worker == WORKER
        assert row.queue == "celery"
        assert row.tenant_id == "tenant-a"
        assert row.result == '{"processed": 3}'
        assert row.received_at and row.started_at and row.finished_at
        assert row.runtime_seconds is not None and row.runtime_seconds >= 0

    def test_a_failure_keeps_exception_and_traceback(self, db_session):
        _received("t2")
        history.on_task_prerun(task_id="t2", task=_task(), args=[], kwargs={})
        history.on_task_failure(task_id="t2", exception=ValueError("boom"), einfo=SimpleNamespace(traceback="Traceback ...\nValueError: boom"))
        history.on_task_postrun(task_id="t2", task=_task(), retval=ValueError("boom"), state="FAILURE")
        row = _row(db_session, "t2")
        assert row.state == "FAILURE"
        assert row.exception == "ValueError('boom')"
        assert "ValueError: boom" in row.traceback
        assert row.result is None

    def test_a_retry_counts_attempts(self, db_session):
        _received("t3")
        history.on_task_retry(request=SimpleNamespace(id="t3", retries=0), reason="broker hiccup", einfo=None)
        row = _row(db_session, "t3")
        assert row.state == "RETRY"
        assert row.retries == 1

    def test_revoked(self, db_session):
        _received("t4")
        history.on_task_revoked(request=SimpleNamespace(id="t4", name=TASK, hostname=WORKER), terminated=True)
        row = _row(db_session, "t4")
        assert row.state == "REVOKED"
        assert row.exception == "terminated"

    def test_a_late_received_never_rolls_back_a_later_state(self, db_session):
        """Received is written by the worker's main process, started by a pool process."""
        history.on_task_prerun(task_id="t5", task=_task(), args=[], kwargs={})
        _received("t5")
        assert _row(db_session, "t5").state == "STARTED"
        history.on_task_postrun(task_id="t5", task=_task(), retval=1, state="SUCCESS")
        history.on_task_prerun(task_id="t5", task=_task(), args=[], kwargs={})
        assert _row(db_session, "t5").state == "SUCCESS"

    def test_secrets_in_arguments_are_redacted_before_storing(self, db_session):
        _received("t6", kwargs={"api_key": "not-a-real-key", "process_instance_id": 7})
        row = _row(db_session, "t6")
        assert "not-a-real-key" not in row.kwargs
        assert '"api_key": "[redacted]"' in row.kwargs

    def test_long_arguments_are_truncated(self, db_session):
        _received("t7", args=["x" * 5000])
        assert len(_row(db_session, "t7").args) == history.ARGS_MAX_CHARS + 1

    def test_disabled_history_writes_nothing(self, db_session, monkeypatch):
        monkeypatch.setenv("M8FLOW_BACKEND_CELERY_TASK_HISTORY_ENABLED", "false")
        _received("t8")
        assert _row(db_session, "t8") is None

    def test_a_recording_failure_never_raises(self, monkeypatch):
        def broken():
            raise RuntimeError("database is down")

        monkeypatch.setattr("m8flow_backend.db.session_scope", broken)
        _received("t9")  # no exception

    def test_old_rows_are_pruned_on_the_write_path(self, db_session, monkeypatch):
        monkeypatch.setattr(history, "PRUNE_EVERY", 1)
        db_session.add(
            CeleryTaskModel(task_id="old", state="SUCCESS", retries=0, updated_at=datetime.now(UTC) - timedelta(days=30))
        )
        db_session.commit()
        _received("new")
        assert _row(db_session, "old") is None
        assert _row(db_session, "new") is not None


def _seed(db_session):
    now = datetime.now(UTC)
    rows = [
        ("a", TASK, "SUCCESS", "celery@worker-1", 0.5, now - timedelta(minutes=5)),
        ("b", TASK, "FAILURE", "celery@worker-1", 1.5, now - timedelta(minutes=4)),
        ("c", "m8flow.notify", "SUCCESS", "celery@worker-2", 2.0, now - timedelta(minutes=3)),
        ("d", "m8flow.notify", "STARTED", "celery@worker-2", None, now - timedelta(minutes=2)),
        ("e", TASK, "SUCCESS", "celery@gone", 0.1, now - timedelta(days=3)),
    ]
    for task_id, name, state, worker, runtime, updated in rows:
        db_session.add(
            CeleryTaskModel(
                task_id=task_id,
                name=name,
                state=state,
                worker=worker,
                retries=0,
                runtime_seconds=runtime,
                kwargs='{"process_instance_id": 42}' if task_id == "c" else "{}",
                updated_at=updated,
            )
        )
    db_session.commit()


class TestReading:
    def test_list_is_newest_first_and_paged(self, db_session):
        _seed(db_session)
        page = Service.list_tasks(page=1, per_page=2)
        assert [row["taskId"] for row in page["results"]] == ["d", "c"]
        assert page["pagination"] == {"page": 1, "perPage": 2, "total": 5, "pages": 3}
        assert "traceback" not in page["results"][0]

    def test_filters_combine(self, db_session):
        _seed(db_session)
        assert [r["taskId"] for r in Service.list_tasks(state="SUCCESS", name=TASK)["results"]] == ["a", "e"]
        assert [r["taskId"] for r in Service.list_tasks(worker="celery@worker-2")["results"]] == ["d", "c"]
        assert [r["taskId"] for r in Service.list_tasks(search="process_instance_id")["results"]] == ["c"]
        assert [r["taskId"] for r in Service.list_tasks(window_hours=24)["results"]] == ["d", "c", "b", "a"]

    def test_get_task_and_404(self, db_session):
        _seed(db_session)
        assert Service.get_task("b")["state"] == "FAILURE"
        assert "traceback" in Service.get_task("b")
        with pytest.raises(ApiError) as exc:
            Service.get_task("missing")
        assert exc.value.status_code == 404

    def test_task_types_aggregate_outcomes_and_runtime(self, db_session):
        _seed(db_session)
        rows = {row["name"]: row for row in Service.task_types(24)}
        assert rows[TASK] | {"lastSeenAt": None} == {
            "name": TASK,
            "total": 2,
            "succeeded": 1,
            "failed": 1,
            "retried": 0,
            "revoked": 0,
            "running": 0,
            "avgRuntimeSeconds": 1.0,
            "maxRuntimeSeconds": 1.5,
            "lastSeenAt": None,
        }
        assert rows["m8flow.notify"]["running"] == 1

    def test_summary_and_recent_workers(self, db_session):
        _seed(db_session)
        assert Service.summary(24) == {"SUCCESS": 2, "FAILURE": 1, "STARTED": 1}
        assert sorted(Service.recent_workers(24)) == ["celery@worker-1", "celery@worker-2"]
        assert "celery@gone" in Service.recent_workers(24 * 7)
