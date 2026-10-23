"""Celery control actions for the System -> Celery page (M8F-602). Super-admin only.

The commands Flower's UI offers, sent through Celery's own ``app.control`` API: revoke or
terminate a task, change a task type's rate or time limit, resize or restart a worker's
pool, start or stop consuming a queue, and shut a worker down. Running an arbitrary task
is deliberately not offered (Flower's UI does not offer it either). Every action is
validated here, gated by ``M8FLOW_BACKEND_CELERY_CONTROL_ENABLED`` and logged with the
acting user.
"""

from __future__ import annotations

import logging
import re

from kombu.exceptions import OperationalError

from m8flow_backend.config import celery_control_enabled
from m8flow_backend.errors import ApiError

try:
    from redis.exceptions import RedisError
except ModuleNotFoundError:  # pragma: no cover - redis ships with celery[redis]
    RedisError = OSError

logger = logging.getLogger("m8flow.celery.control")

REPLY_TIMEOUT_SECONDS = 2.0
WORKER_ACTIONS = ("pool_grow", "pool_shrink", "autoscale", "pool_restart", "add_consumer", "cancel_consumer", "shutdown")
TERMINATE_SIGNALS = ("SIGTERM", "SIGKILL", "SIGINT")
MAX_POOL_STEP = 32
MAX_AUTOSCALE = 64

_BROKER_ERRORS = (OperationalError, OSError, RedisError)
# Used with fullmatch: "$" would also accept a trailing newline.
_RATE_LIMIT_RE = re.compile(r"\d+(\.\d+)?(/[smh])?")
_NAME_RE = re.compile(r"[\w.:@\-\[\]]{1,255}")


def _invalid(message: str) -> ApiError:
    return ApiError(error_code="invalid_parameter", message=message, status_code=400)


def _require_enabled() -> None:
    if not celery_control_enabled():
        raise ApiError(
            error_code="celery_control_disabled",
            message="Celery control actions are disabled on this deployment.",
            status_code=403,
        )


def _name(value: object, what: str) -> str:
    text = str(value or "").strip()
    if not _NAME_RE.fullmatch(text):
        raise _invalid(f"'{what}' is missing or contains characters it cannot have.")
    return text


def _for_log(value: object) -> str:
    """Line breaks escaped, so a logged value cannot start a forged log line. The names
    are validated already; this keeps the audit line safe if that ever changes."""
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def _limit_destination(task_name: str, worker: object) -> tuple[list[str] | None, str]:
    """No worker means every worker, as Celery broadcasts by default."""
    if worker is None or worker == "":
        return None, task_name
    name = _name(worker, "worker")
    return [name], f"{task_name} on {name}"


def _whole(value: object, what: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise _invalid(f"'{what}' must be a whole number.")
    if not low <= int(value) <= high:
        raise _invalid(f"'{what}' must be between {low} and {high}.")
    return int(value)


def _seconds(value: object, what: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise _invalid(f"'{what}' must be a number of seconds, 0 or more.")
    return float(value)


def summarize_replies(replies: object) -> dict:
    """``[{worker: {"ok": msg} | {"error": msg}}]`` -> ``{ok, message, results}``."""
    results = []
    for reply in replies if isinstance(replies, list) else []:
        for worker, body in (reply or {}).items():
            succeeded = isinstance(body, dict) and "ok" in body
            message = (body.get("ok") if succeeded else body.get("error")) if isinstance(body, dict) else body
            results.append({"worker": str(worker), "ok": succeeded, "message": str(message)})
    if not results:
        return {"ok": False, "message": "No worker answered.", "results": []}
    ok = all(result["ok"] for result in results)
    return {"ok": ok, "message": results[0]["message"] if len(results) == 1 else None, "results": results}


def _send(command: str, *args, actor: str, target: str, destination: list[str] | None = None, reply: bool = True, **kwargs) -> dict:
    from m8flow_backend.scheduler import celery_app

    _require_enabled()
    try:
        with celery_app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=1)
            replies = getattr(celery_app.control, command)(
                *args, destination=destination, connection=conn, reply=reply, timeout=REPLY_TIMEOUT_SECONDS, **kwargs
            )
    except _BROKER_ERRORS as e:
        logger.warning("celery control: broker unreachable for %s on %s: %s", command, _for_log(target), e)
        raise ApiError(
            error_code="celery_monitoring_unavailable",
            message="The Celery broker is not reachable, so the command was not sent.",
            status_code=503,
        )
    outcome = summarize_replies(replies) if reply else {"ok": True, "message": "Sent.", "results": []}
    logger.info(
        "celery control: %s on %s by %s -> %s",
        command,
        _for_log(target),
        _for_log(actor),
        "ok" if outcome["ok"] else _for_log(outcome),
    )
    return outcome


class CeleryControlService:
    @staticmethod
    def revoke(task_id: object, *, terminate: bool, signal: object, actor: str) -> dict:
        task = _name(task_id, "taskId")
        signal_name = str(signal or "SIGTERM").upper()
        if signal_name not in TERMINATE_SIGNALS:
            raise _invalid(f"'signal' must be one of {', '.join(TERMINATE_SIGNALS)}.")
        return _send("revoke", task, actor=actor, target=task, terminate=bool(terminate), signal=signal_name)

    @staticmethod
    def rate_limit(task_name: object, rate_limit: object, *, actor: str, worker: object = None) -> dict:
        """Every worker, or only ``worker`` (Flower's per-worker Limits tab)."""
        name = _name(task_name, "taskName")
        text = str(rate_limit or "").strip()
        if text and not _RATE_LIMIT_RE.fullmatch(text):
            raise _invalid("'rateLimit' must look like 10, 10/s, 10/m or 10/h; leave it empty to remove the limit.")
        destination, target = _limit_destination(name, worker)
        return _send("rate_limit", name, text or None, destination=destination, actor=actor, target=target)

    @staticmethod
    def time_limit(task_name: object, soft: object, hard: object, *, actor: str, worker: object = None) -> dict:
        name = _name(task_name, "taskName")
        soft_seconds = _seconds(soft, "softSeconds")
        hard_seconds = _seconds(hard, "hardSeconds")
        if soft_seconds is not None and hard_seconds is not None and soft_seconds > hard_seconds:
            raise _invalid("'softSeconds' cannot be longer than 'hardSeconds'.")
        destination, target = _limit_destination(name, worker)
        return _send("time_limit", name, soft=soft_seconds, hard=hard_seconds, destination=destination, actor=actor, target=target)

    @staticmethod
    def worker_action(worker_name: object, body: dict, *, actor: str) -> dict:
        worker = _name(worker_name, "worker")
        action = str(body.get("action") or "")
        destination = [worker]
        target = f"{worker}"
        if action == "pool_grow":
            return _send("pool_grow", _whole(body.get("n", 1), "n", 1, MAX_POOL_STEP), destination=destination, actor=actor, target=target)
        if action == "pool_shrink":
            return _send("pool_shrink", _whole(body.get("n", 1), "n", 1, MAX_POOL_STEP), destination=destination, actor=actor, target=target)
        if action == "autoscale":
            minimum = _whole(body.get("min"), "min", 0, MAX_AUTOSCALE)
            maximum = _whole(body.get("max"), "max", 1, MAX_AUTOSCALE)
            if minimum > maximum:
                raise _invalid("'min' cannot be more than 'max'.")
            return _send("autoscale", maximum, minimum, destination=destination, actor=actor, target=target)
        if action == "pool_restart":
            return _send("pool_restart", destination=destination, actor=actor, target=target)
        if action in ("add_consumer", "cancel_consumer"):
            queue = _name(body.get("queue"), "queue")
            return _send(action, queue, destination=destination, actor=actor, target=f"{worker} queue {queue}")
        if action == "shutdown":
            # The worker exits without replying, so there is nothing to wait for.
            return _send("shutdown", destination=destination, reply=False, actor=actor, target=target)
        raise _invalid(f"'action' must be one of {', '.join(WORKER_ACTIONS)}.")
