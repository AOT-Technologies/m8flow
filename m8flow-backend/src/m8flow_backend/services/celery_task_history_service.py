"""Celery task history: recorded by the worker, read by the System -> Celery page.

Celery keeps no task history; Flower rebuilds one in memory from worker events and loses
it on restart. m8flow records the same lifecycle (received, started, succeeded, failed,
retried, revoked) straight from the worker's own task signals into
``m8flow_celery_task``, so history survives restarts and needs no extra service.

Writes are best effort: a recording failure is logged and swallowed, because history
must never break a task. Arguments, results and tracebacks are redacted before they are
stored, then truncated.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, delete, func, or_, select

from m8flow_backend.config import celery_task_history_enabled, celery_task_history_retention_days
from m8flow_backend.errors import ApiError
from m8flow_backend.models.celery_task import FINISHED_STATES, CeleryTaskModel, CeleryTaskState
from m8flow_backend.services.nats_monitoring_service import redact_secrets

logger = logging.getLogger("m8flow.celery.history")

ARGS_MAX_CHARS = 2000
RESULT_MAX_CHARS = 2000
EXCEPTION_MAX_CHARS = 2000
TRACEBACK_MAX_CHARS = 10000
MAX_PER_PAGE = 100

# Pruning runs on the write path every this many writes per process, so a worker that
# runs tasks keeps the table bounded without a separate scheduled job.
PRUNE_EVERY = 500

# A write may arrive after a later one (the worker's main process records "received",
# a pool process records "started"). These states are never overwritten by the state
# on the left.
_KEEP_EXISTING: dict[str, tuple[str, ...]] = {
    CeleryTaskState.RECEIVED.value: (CeleryTaskState.STARTED.value, *FINISHED_STATES),
    CeleryTaskState.STARTED.value: FINISHED_STATES,
    CeleryTaskState.RETRY.value: FINISHED_STATES,
}

_writes = 0
_writes_lock = threading.Lock()
_started: dict[str, float] = {}  # task id -> perf_counter at prerun, in this pool process


def _now() -> datetime:
    return datetime.now(UTC)


def _store(value: object, cap: int) -> str | None:
    """Redact, then truncate; never the other way round, or a cut could leave half a secret."""
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = redact_secrets(text)
    return text if len(text) <= cap else text[:cap] + "…"


def _iso(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else None


def _tenant(request: object) -> str | None:
    """The tenant header, wherever this Celery version put it on the request."""
    # Imported here: importing the scheduler package builds the Celery app, which installs
    # this module's signals.
    from m8flow_backend.scheduler.celery_tenant import tenant_id_from_celery_headers

    for source in (
        getattr(request, "request_dict", None),
        getattr(request, "headers", None),
        getattr(request, "__dict__", None),
    ):
        tenant_id = tenant_id_from_celery_headers(source)
        if tenant_id:
            return tenant_id
    return None


def _insert_for(dialect: str):
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert


def _upsert(session, task_id: str, values: dict) -> None:
    values = {key: value for key, value in values.items() if value is not None}
    values["updated_at"] = _now()
    table = CeleryTaskModel.__table__
    insert = _insert_for(session.get_bind().dialect.name)
    # A first write that is not "received" (eager runs, a missed signal) still needs a state.
    stmt = insert(table).values(
        task_id=task_id,
        **{"retries": 0, "state": CeleryTaskState.STARTED.value, **values},
    )
    updates = {key: stmt.excluded[key] for key in values}
    keep = _KEEP_EXISTING.get(values.get("state", ""))
    if keep:
        updates["state"] = case((table.c.state.in_(keep), table.c.state), else_=stmt.excluded.state)
    session.execute(stmt.on_conflict_do_update(index_elements=["task_id"], set_=updates))


def _prune(session) -> None:
    days = celery_task_history_retention_days()
    if days > 0:
        session.execute(delete(CeleryTaskModel).where(CeleryTaskModel.updated_at < _now() - timedelta(days=days)))


def record(task_id: str | None, **values) -> None:
    """Upsert one task's row. Best effort: history must never break a task."""
    global _writes
    if not task_id or not celery_task_history_enabled():
        return
    try:
        from m8flow_backend.db import session_scope

        with session_scope() as session:
            _upsert(session, task_id, values)
            with _writes_lock:
                _writes += 1
                due = _writes % PRUNE_EVERY == 0
            if due:
                _prune(session)
    except Exception as e:  # noqa: BLE001 - recording must not fail the task
        logger.warning("celery task history: could not record %s: %s", task_id, e)


# ------------------------------------------------------------------ signals


def on_task_received(sender=None, request=None, **_kwargs) -> None:
    """Worker main process, as soon as the message arrives."""
    if request is None:
        return
    request_dict = getattr(request, "request_dict", None) or {}
    record(
        getattr(request, "id", None),
        state=CeleryTaskState.RECEIVED.value,
        name=getattr(request, "name", None),
        worker=getattr(request, "hostname", None),
        queue=(getattr(request, "delivery_info", None) or {}).get("routing_key"),
        tenant_id=_tenant(request),
        args=_store(getattr(request, "args", None), ARGS_MAX_CHARS),
        kwargs=_store(getattr(request, "kwargs", None), ARGS_MAX_CHARS),
        retries=int(request_dict.get("retries") or 0),
        eta=_iso(getattr(request, "eta", None)),
        expires=_iso(getattr(request, "expires", None)),
        parent_id=getattr(request, "parent_id", None),
        root_id=getattr(request, "root_id", None),
        received_at=_now(),
    )


def on_task_prerun(sender=None, task_id=None, task=None, args=None, kwargs=None, **_kwargs) -> None:
    """Pool process, right before the task body runs."""
    if task_id:
        _started[task_id] = time.perf_counter()
    request = getattr(task, "request", None)
    record(
        task_id,
        state=CeleryTaskState.STARTED.value,
        name=getattr(task, "name", None),
        worker=getattr(request, "hostname", None),
        queue=(getattr(request, "delivery_info", None) or {}).get("routing_key"),
        tenant_id=_tenant(request),
        args=_store(args, ARGS_MAX_CHARS),
        kwargs=_store(kwargs, ARGS_MAX_CHARS),
        started_at=_now(),
    )


def on_task_postrun(sender=None, task_id=None, task=None, retval=None, state=None, **_kwargs) -> None:
    """Pool process, after the task body returns or raises. ``state`` is final here."""
    started = _started.pop(task_id, None) if task_id else None
    record(
        task_id,
        state=state or None,
        result=_store(retval, RESULT_MAX_CHARS) if state == CeleryTaskState.SUCCESS.value else None,
        finished_at=_now() if state in FINISHED_STATES else None,
        runtime_seconds=round(time.perf_counter() - started, 6) if started is not None else None,
    )


def on_task_failure(sender=None, task_id=None, exception=None, einfo=None, **_kwargs) -> None:
    record(
        task_id,
        state=CeleryTaskState.FAILURE.value,
        exception=_store(repr(exception), EXCEPTION_MAX_CHARS) if exception is not None else None,
        traceback=_store(getattr(einfo, "traceback", None), TRACEBACK_MAX_CHARS),
    )


def on_task_retry(sender=None, request=None, reason=None, einfo=None, **_kwargs) -> None:
    record(
        getattr(request, "id", None),
        state=CeleryTaskState.RETRY.value,
        retries=int(getattr(request, "retries", 0) or 0) + 1,
        exception=_store(str(reason), EXCEPTION_MAX_CHARS) if reason is not None else None,
        traceback=_store(getattr(einfo, "traceback", None), TRACEBACK_MAX_CHARS),
    )


def on_task_revoked(sender=None, request=None, terminated=None, signum=None, expired=None, **_kwargs) -> None:
    reason = "expired" if expired else ("terminated" if terminated else "revoked")
    record(
        getattr(request, "id", None),
        state=CeleryTaskState.REVOKED.value,
        name=getattr(request, "name", None),
        worker=getattr(request, "hostname", None),
        exception=reason,
        finished_at=_now(),
    )


def on_worker_process_init(**_kwargs) -> None:
    from m8flow_backend.db import forget_engine_after_fork

    forget_engine_after_fork()


_SIGNALS_INSTALLED = False


def install_celery_task_history_signals() -> None:
    global _SIGNALS_INSTALLED
    if _SIGNALS_INSTALLED:
        return
    from celery import signals

    signals.task_received.connect(on_task_received, weak=False)
    signals.task_prerun.connect(on_task_prerun, weak=False)
    signals.task_postrun.connect(on_task_postrun, weak=False)
    signals.task_failure.connect(on_task_failure, weak=False)
    signals.task_retry.connect(on_task_retry, weak=False)
    signals.task_revoked.connect(on_task_revoked, weak=False)
    signals.worker_process_init.connect(on_worker_process_init, weak=False)
    _SIGNALS_INSTALLED = True


# ------------------------------------------------------------------ reading


def _row(task: CeleryTaskModel, *, full: bool) -> dict:
    row = {
        "taskId": task.task_id,
        "name": task.name,
        "state": task.state,
        "worker": task.worker,
        "queue": task.queue,
        "tenantId": task.tenant_id,
        "args": task.args or "",
        "kwargs": task.kwargs or "",
        "retries": task.retries or 0,
        "receivedAt": _iso(task.received_at),
        "startedAt": _iso(task.started_at),
        "finishedAt": _iso(task.finished_at),
        "runtimeSeconds": task.runtime_seconds,
        "updatedAt": _iso(task.updated_at),
        "exception": task.exception,
    }
    if full:
        row |= {
            "result": task.result,
            "traceback": task.traceback,
            "eta": task.eta,
            "expires": task.expires,
            "parentId": task.parent_id,
            "rootId": task.root_id,
        }
    return row


def _cutoff(window_hours: int | None) -> datetime | None:
    return _now() - timedelta(hours=window_hours) if window_hours and window_hours > 0 else None


class CeleryTaskHistoryService:
    @staticmethod
    def list_tasks(
        *,
        state: str | None = None,
        name: str | None = None,
        worker: str | None = None,
        search: str | None = None,
        window_hours: int | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        from m8flow_backend.db import current_session

        page = max(1, page)
        per_page = min(max(1, per_page), MAX_PER_PAGE)
        stmt = select(CeleryTaskModel)
        if state:
            stmt = stmt.where(CeleryTaskModel.state == state)
        if name:
            stmt = stmt.where(CeleryTaskModel.name == name)
        if worker:
            stmt = stmt.where(CeleryTaskModel.worker == worker)
        cutoff = _cutoff(window_hours)
        if cutoff is not None:
            stmt = stmt.where(CeleryTaskModel.updated_at >= cutoff)
        if search and search.strip():
            needle = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    CeleryTaskModel.task_id.ilike(needle),
                    CeleryTaskModel.name.ilike(needle),
                    CeleryTaskModel.args.ilike(needle),
                    CeleryTaskModel.kwargs.ilike(needle),
                )
            )
        session = current_session()
        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = session.scalars(
            stmt.order_by(CeleryTaskModel.updated_at.desc(), CeleryTaskModel.task_id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        return {
            "results": [_row(task, full=False) for task in rows],
            "pagination": {"page": page, "perPage": per_page, "total": total, "pages": -(-total // per_page)},
        }

    @staticmethod
    def get_task(task_id: str) -> dict:
        from m8flow_backend.db import current_session

        task = current_session().get(CeleryTaskModel, task_id)
        if task is None:
            raise ApiError(error_code="celery_task_not_found", message="No recorded task with that id.", status_code=404)
        return _row(task, full=True)

    @staticmethod
    def task_types(window_hours: int = 24) -> list[dict]:
        from m8flow_backend.db import current_session

        model = CeleryTaskModel

        def count(state: CeleryTaskState):
            return func.sum(case((model.state == state.value, 1), else_=0))

        stmt = (
            select(
                model.name,
                func.count(),
                count(CeleryTaskState.SUCCESS),
                count(CeleryTaskState.FAILURE),
                count(CeleryTaskState.RETRY),
                count(CeleryTaskState.REVOKED),
                count(CeleryTaskState.STARTED),
                func.avg(model.runtime_seconds),
                func.max(model.runtime_seconds),
                func.max(model.updated_at),
            )
            .where(model.name.is_not(None))
            .group_by(model.name)
            .order_by(model.name)
        )
        cutoff = _cutoff(window_hours)
        if cutoff is not None:
            stmt = stmt.where(model.updated_at >= cutoff)
        return [
            {
                "name": name,
                "total": int(total or 0),
                "succeeded": int(succeeded or 0),
                "failed": int(failed or 0),
                "retried": int(retried or 0),
                "revoked": int(revoked or 0),
                "running": int(running or 0),
                "avgRuntimeSeconds": round(float(avg), 6) if avg is not None else None,
                "maxRuntimeSeconds": round(float(maximum), 6) if maximum is not None else None,
                "lastSeenAt": _iso(last_seen),
            }
            for name, total, succeeded, failed, retried, revoked, running, avg, maximum, last_seen in current_session().execute(stmt)
        ]

    @staticmethod
    def summary(window_hours: int = 24) -> dict:
        from m8flow_backend.db import current_session

        stmt = select(CeleryTaskModel.state, func.count()).group_by(CeleryTaskModel.state)
        cutoff = _cutoff(window_hours)
        if cutoff is not None:
            stmt = stmt.where(CeleryTaskModel.updated_at >= cutoff)
        return {state: int(n) for state, n in current_session().execute(stmt)}

    @staticmethod
    def recent_workers(window_hours: int = 24) -> dict[str, str | None]:
        """Workers that recorded a task in the window, with when they were last seen."""
        from m8flow_backend.db import current_session

        stmt = (
            select(CeleryTaskModel.worker, func.max(CeleryTaskModel.updated_at))
            .where(CeleryTaskModel.worker.is_not(None))
            .group_by(CeleryTaskModel.worker)
        )
        cutoff = _cutoff(window_hours)
        if cutoff is not None:
            stmt = stmt.where(CeleryTaskModel.updated_at >= cutoff)
        return {worker: _iso(last_seen) for worker, last_seen in current_session().execute(stmt)}
