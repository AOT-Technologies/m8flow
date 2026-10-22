"""Reads live Celery worker state for the System -> Celery page.

Everything here is read-only: Celery's own ``inspect`` broadcasts over the broker, plus
Redis queue and unacked counts. Control actions live in ``celery_control_service`` and
task history in ``celery_task_history_service``. Nothing reaches a browser except what
the normalizers below choose to pass on.

The parsing was written against a real Celery 5.6.3 reply captured from a running worker
(``tests/unit/m8flow_backend/fixtures/celery_inspect.json``), not from the documentation.
That capture settled three things:

- ``active(safe=True)`` turns arguments into Python ``repr`` strings, which secret
  redaction cannot parse, and ``reserved`` / ``scheduled`` ignore ``safe`` and return raw
  values anyway. So every list is read raw and redacted structurally here.
- A revoked task that has not reached its turn is still listed under ``reserved``.
- ``stats.broker`` describes the broker connection (host, port, user), and ``conf``
  carries the broker URL. Neither is passed on as-is.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone

from kombu.exceptions import OperationalError

from m8flow_backend.config import celery_control_enabled, celery_monitoring_enabled, celery_task_history_enabled
from m8flow_backend.errors import ApiError
from m8flow_backend.services.nats_monitoring_service import _SECRET_NAME_RE, redact_secrets

try:
    from redis.exceptions import RedisError
except ModuleNotFoundError:  # pragma: no cover - redis ships with celery[redis]
    RedisError = OSError

logger = logging.getLogger("m8flow.celery.monitoring")

# A broadcast waits this long for worker replies. Once ping has counted the workers, the
# other calls return as soon as every one of them has answered.
INSPECT_TIMEOUT_SECONDS = 1.0

# Every inspect call is a broadcast to every worker, so several admins polling must not
# multiply it.
# ponytail: per-process cache; move it to Redis if many backend replicas poll at once.
CACHE_SECONDS = 5.0

# Live task arguments can carry workflow data: previews are redacted first, then cut to this.
ARGS_PREVIEW_MAX_CHARS = 500

# History window behind the overview's succeeded / failed counts and offline workers.
HISTORY_WINDOW_HOURS = 24

_BROKER_ERRORS = (OperationalError, OSError, RedisError)
_TASK_LISTS = ("active", "reserved", "scheduled")
_INSPECT_CALLS = ("stats", "active_queues", "registered", "conf", *_TASK_LISTS, "revoked")
_URL_CREDENTIALS_RE = re.compile(r"(\w[\w+.-]*://)([^:/@\s]*):([^@/\s]+)@")
_RUSAGE_FIELDS = ("utime", "stime", "maxrss", "minflt", "majflt", "nvcsw", "nivcsw")

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "snapshot": None}


def _unavailable(message: str) -> ApiError:
    """A 503 written for the person looking at the page; the cause is only logged."""
    return ApiError(error_code="celery_monitoring_unavailable", message=message, status_code=503)


_UNREACHABLE_MESSAGE = (
    "The Celery broker is not reachable. Redis may be stopped or still starting. "
    "Check that Redis is running and that M8FLOW_BACKEND_CELERY_BROKER_URL points at it."
)


def _require_enabled() -> None:
    if not celery_monitoring_enabled():
        raise ApiError(
            error_code="celery_monitoring_disabled",
            message="Celery monitoring is not enabled on this deployment.",
            status_code=503,
        )


def _int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _iso_epoch(seconds: object) -> str | None:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def _preview(value: object) -> str:
    """Arguments as redacted, length-capped text. Redact before cutting, so a cut can
    never leave half a secret behind."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = redact_secrets(text)
    return text if len(text) <= ARGS_PREVIEW_MAX_CHARS else text[:ARGS_PREVIEW_MAX_CHARS] + "…"


def _pool_name(implementation: object) -> str | None:
    """``celery.concurrency.prefork:TaskPool`` -> ``prefork``."""
    if not isinstance(implementation, str) or not implementation:
        return None
    return implementation.rsplit(".", 1)[-1].split(":", 1)[0]


def _per_worker(snapshot: dict, key: str) -> dict:
    value = snapshot.get(key)
    return value if isinstance(value, dict) else {}


def redact_conf(conf: dict) -> list[dict]:
    """A worker's configuration as key/value rows, safe to show.

    Keys that name a secret are replaced, and any URL keeps its scheme, user and host but
    loses its password (``redis://:secret@redis:6379/0`` -> ``redis://:***@redis:6379/0``).
    """
    rows = []
    for key in sorted(conf):
        value = conf[key]
        if _SECRET_NAME_RE.search(str(key)):
            text = "[redacted]"
        else:
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
            text = _URL_CREDENTIALS_RE.sub(r"\1\2:***@", redact_secrets(text))
        rows.append({"key": str(key), "value": text})
    return rows


def _collect() -> dict:
    """One round of inspect calls on a single broker connection."""
    from m8flow_backend.scheduler import celery_app  # importing builds the Celery app

    snapshot: dict = {name: {} for name in ("ping", *_INSPECT_CALLS)}
    try:
        with celery_app.connection_for_write() as conn:
            # Fail fast instead of kombu's default retry loop: a page that reports the
            # broker as down beats one that hangs.
            conn.ensure_connection(max_retries=1)
            snapshot["transport"] = conn.transport.driver_type
            snapshot["ping"] = celery_app.control.inspect(timeout=INSPECT_TIMEOUT_SECONDS, connection=conn).ping() or {}
            if snapshot["ping"]:
                inspect = celery_app.control.inspect(
                    timeout=INSPECT_TIMEOUT_SECONDS, connection=conn, limit=len(snapshot["ping"])
                )
                for name in _INSPECT_CALLS:
                    snapshot[name] = getattr(inspect, name)() or {}
            snapshot["broker"] = _broker_counts(conn, snapshot, celery_app.conf.task_default_queue)
    except _BROKER_ERRORS as e:
        logger.warning("celery monitoring: broker unreachable: %s", e)
        raise _unavailable(_UNREACHABLE_MESSAGE)
    snapshot["captured_at"] = datetime.now(timezone.utc).isoformat()
    return snapshot


def _broker_counts(conn, snapshot: dict, default_queue: str) -> dict:
    """Waiting messages per queue, the workers consuming each, and unacked messages."""
    consumers: dict[str, set[str]] = {}
    for worker, queues in _per_worker(snapshot, "active_queues").items():
        for queue in queues or []:
            if isinstance(queue, dict) and queue.get("name"):
                consumers.setdefault(queue["name"], set()).add(worker)
    names = sorted(consumers) or [default_queue]
    queues = [{"name": name, "messages": None, "consumers": sorted(consumers.get(name, ()))} for name in names]
    if snapshot.get("transport") != "redis":
        return {"queues": queues, "unacked": None}
    # A channel of its own: the default channel just consumed the inspect replies with a
    # blocking BRPOP, and a command on that client corrupts the read kombu does on close.
    # ponytail: counts the default-priority list only; m8flow publishes no task priorities.
    with conn.channel() as channel:
        for queue in queues:
            queue["messages"] = _int(channel.client.llen(queue["name"]))
        unacked = _int(channel.client.hlen(getattr(channel, "unacked_key", "unacked")))
    return {"queues": queues, "unacked": unacked}


class CeleryMonitoringService:
    @classmethod
    def _snapshot(cls) -> dict:
        _require_enabled()
        # Held while collecting: a second caller waits and gets the fresh snapshot rather
        # than sending its own broadcast. A failure is not cached.
        with _lock:
            if _cache["snapshot"] is not None and time.monotonic() - _cache["at"] < CACHE_SECONDS:
                return _cache["snapshot"]
            snapshot = _collect()
            _cache.update(at=time.monotonic(), snapshot=snapshot)
            return snapshot

    @staticmethod
    def _history_or_empty(read) -> dict:
        """History is optional: a disabled or not-yet-migrated table must not blank the page."""
        if not celery_task_history_enabled():
            return {}
        try:
            return read()
        except Exception as e:  # noqa: BLE001
            logger.warning("celery monitoring: task history unavailable: %s", e)
            return {}

    @classmethod
    def overview(cls) -> dict:
        from m8flow_backend.services.celery_task_history_service import CeleryTaskHistoryService

        snapshot = cls._snapshot()
        overview = cls.normalize_overview(snapshot)
        recent = cls._history_or_empty(lambda: CeleryTaskHistoryService.recent_workers(HISTORY_WINDOW_HOURS))
        counts = cls._history_or_empty(lambda: CeleryTaskHistoryService.summary(HISTORY_WINDOW_HOURS))
        online = set(_per_worker(snapshot, "ping"))
        return {
            **overview,
            "workersOffline": len(set(recent) - online),
            "history": {
                "windowHours": HISTORY_WINDOW_HOURS,
                "succeeded": counts.get("SUCCESS", 0),
                "failed": counts.get("FAILURE", 0),
                "retried": counts.get("RETRY", 0),
                "revoked": counts.get("REVOKED", 0),
            },
            "historyEnabled": celery_task_history_enabled(),
            "controlEnabled": celery_control_enabled(),
        }

    @classmethod
    def workers(cls) -> dict:
        from m8flow_backend.services.celery_task_history_service import CeleryTaskHistoryService

        snapshot = cls._snapshot()
        recent = cls._history_or_empty(lambda: CeleryTaskHistoryService.recent_workers(HISTORY_WINDOW_HOURS))
        return {"results": cls.normalize_workers(snapshot, recent), "capturedAt": snapshot.get("captured_at")}

    @classmethod
    def tasks(cls) -> dict:
        return cls.normalize_tasks(cls._snapshot())

    @classmethod
    def broker(cls) -> dict:
        snapshot = cls._snapshot()
        return {
            **(snapshot.get("broker") or {"queues": [], "unacked": None}),
            "transport": snapshot.get("transport"),
            "capturedAt": snapshot.get("captured_at"),
        }

    @classmethod
    def registered_task_names(cls) -> set[str]:
        """Task names any online worker can run; empty when the broker is unreachable."""
        try:
            snapshot = cls._snapshot()
        except ApiError:
            return set()
        return {str(name) for names in _per_worker(snapshot, "registered").values() for name in names or []}

    # ------------------------------------------------------- normalization

    @staticmethod
    def normalize_overview(snapshot: dict) -> dict:
        stats = _per_worker(snapshot, "stats")
        broker = snapshot.get("broker") or {}

        def count(key: str) -> int:
            return sum(len(rows or []) for rows in _per_worker(snapshot, key).values())

        return {
            "workersOnline": len(_per_worker(snapshot, "ping")),
            "concurrency": sum(_int((s.get("pool") or {}).get("max-concurrency")) for s in stats.values()),
            "tasksRunning": count("active"),
            "tasksReserved": count("reserved"),
            "tasksScheduled": count("scheduled"),
            "tasksProcessed": sum(_int(v) for s in stats.values() for v in (s.get("total") or {}).values()),
            "queues": broker.get("queues") or [],
            "unacked": broker.get("unacked"),
            "transport": snapshot.get("transport"),
            "capturedAt": snapshot.get("captured_at"),
        }

    @staticmethod
    def normalize_workers(snapshot: dict, recent: dict[str, str | None] | None = None) -> list[dict]:
        """One row per worker that answered ping, then one per worker seen in task history
        that no longer answers. Fields are picked, never copied whole, so connection
        details in ``stats.broker`` cannot reach the browser."""
        stats = _per_worker(snapshot, "stats")
        online = sorted(_per_worker(snapshot, "ping"))
        rows = []
        for name in online:
            worker = stats.get(name) or {}
            pool = worker.get("pool") or {}
            totals = worker.get("total") or {}
            queues = _per_worker(snapshot, "active_queues").get(name) or []
            autoscaler = worker.get("autoscaler") if isinstance(worker.get("autoscaler"), dict) else None
            rusage = worker.get("rusage") if isinstance(worker.get("rusage"), dict) else {}
            timeouts = pool.get("timeouts") if isinstance(pool.get("timeouts"), (list, tuple)) else []
            conf = _per_worker(snapshot, "conf").get(name)
            rows.append(
                {
                    "name": name,
                    "online": True,
                    "lastSeenAt": snapshot.get("captured_at"),
                    "pid": worker.get("pid"),
                    "uptimeSeconds": _int(worker.get("uptime")),
                    "pool": _pool_name(pool.get("implementation")),
                    "concurrency": _int(pool.get("max-concurrency")),
                    "processes": len(pool.get("processes") or []),
                    "maxTasksPerChild": pool.get("max-tasks-per-child")
                    if isinstance(pool.get("max-tasks-per-child"), int)
                    else None,
                    "softTimeLimitSeconds": timeouts[0] if len(timeouts) > 0 else None,
                    "hardTimeLimitSeconds": timeouts[1] if len(timeouts) > 1 else None,
                    "autoscaleMin": _int(autoscaler.get("min")) if autoscaler else None,
                    "autoscaleMax": _int(autoscaler.get("max")) if autoscaler else None,
                    "prefetchCount": _int(worker.get("prefetch_count")),
                    "tasksProcessed": sum(_int(v) for v in totals.values()),
                    "tasksProcessedByName": {str(k): _int(v) for k, v in sorted(totals.items())},
                    "queues": sorted(q.get("name") for q in queues if isinstance(q, dict) and q.get("name")),
                    "registeredTasks": sorted(str(t) for t in _per_worker(snapshot, "registered").get(name) or []),
                    "running": len(_per_worker(snapshot, "active").get(name) or []),
                    "reserved": len(_per_worker(snapshot, "reserved").get(name) or []),
                    "scheduled": len(_per_worker(snapshot, "scheduled").get(name) or []),
                    "system": {field: rusage[field] for field in _RUSAGE_FIELDS if field in rusage},
                    "conf": redact_conf(conf) if isinstance(conf, dict) else [],
                }
            )
        for name, last_seen in sorted((recent or {}).items()):
            if name not in online:
                rows.append({"name": name, "online": False, "lastSeenAt": last_seen})
        return rows

    @staticmethod
    def normalize_tasks(snapshot: dict) -> dict:
        revoked = sorted(
            {str(task_id) for ids in _per_worker(snapshot, "revoked").values() for task_id in ids or []}
        )
        revoked_set = set(revoked)

        def row(worker: str, request: dict, eta: object = None) -> dict:
            task_id = request.get("id")
            return {
                "id": task_id,
                "name": request.get("name") or request.get("type"),
                "worker": worker,
                "queue": (request.get("delivery_info") or {}).get("routing_key"),
                "startedAt": _iso_epoch(request.get("time_start")),
                "eta": eta if isinstance(eta, str) else None,
                "acknowledged": bool(request.get("acknowledged")),
                "revoked": task_id in revoked_set,
                "args": _preview(request.get("args")),
                "kwargs": _preview(request.get("kwargs")),
            }

        result: dict = {key: [] for key in _TASK_LISTS}
        for key in _TASK_LISTS:
            for worker, entries in sorted(_per_worker(snapshot, key).items()):
                for entry in entries or []:
                    if not isinstance(entry, dict):
                        continue
                    if key == "scheduled":  # {"eta", "priority", "request": {...}}
                        result[key].append(row(worker, entry.get("request") or {}, entry.get("eta")))
                    else:
                        result[key].append(row(worker, entry))
        return {**result, "revoked": revoked, "capturedAt": snapshot.get("captured_at")}
