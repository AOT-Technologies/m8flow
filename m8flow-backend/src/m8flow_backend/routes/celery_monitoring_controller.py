"""Celery monitoring and control endpoints for the System -> Celery page. Super-admin only.

Reads (``GET /m8flow/celery/*``) are gated by the ``read-celery-monitoring`` grant and
control actions (``POST /m8flow/celery/control/*``) by ``manage-celery-monitoring``, both
super-admin only with no group fallback (``config/permissions/m8flow.yml``). Worker state
and task history cover every tenant, so each handler also requires super-admin outright,
as the NATS broker views do.
"""

from __future__ import annotations

from flask import request

from m8flow_backend.auth import is_super_admin_request, require_current_user
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.config import celery_task_history_enabled
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_backend.services.celery_control_service import CeleryControlService
from m8flow_backend.services.celery_monitoring_service import CeleryMonitoringService
from m8flow_backend.services.celery_task_history_service import CeleryTaskHistoryService

# YAML is the only grant: the editor/tenant-admin identifier fallback must not open these.
_gate = require_permission(group_fallback=False)


def _require_super_admin() -> str:
    """Returns the acting user's name, for the control audit log."""
    user = require_current_user()
    if not is_super_admin_request():
        raise ApiError(
            error_code="forbidden",
            message="Celery monitoring is restricted to super-admins.",
            status_code=403,
        )
    return str(getattr(user, "username", None) or getattr(user, "id", "unknown"))


def _require_history() -> None:
    if not celery_task_history_enabled():
        raise ApiError(
            error_code="celery_history_disabled",
            message="Celery task history is not enabled on this deployment.",
            status_code=503,
        )


def _int_arg(name: str, default: int | None = None) -> int | None:
    raw = request.args.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ApiError(error_code="invalid_parameter", message=f"'{name}' must be an integer.", status_code=400)


def _body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


@handle_api_errors
@_gate
def overview() -> tuple:
    """Workers online and offline, task counts, last-24-hour outcomes and queue depth."""
    _require_super_admin()
    return success_response(CeleryMonitoringService.overview())


@handle_api_errors
@_gate
def workers() -> tuple:
    """Every worker with pool, queues, registered tasks, system usage and config."""
    _require_super_admin()
    return success_response(CeleryMonitoringService.workers())


@handle_api_errors
@_gate
def tasks() -> tuple:
    """Running, prefetched and scheduled tasks right now, plus revoked ids."""
    _require_super_admin()
    return success_response(CeleryMonitoringService.tasks())


@handle_api_errors
@_gate
def broker() -> tuple:
    """Queues with waiting messages and consumers, and unacknowledged messages."""
    _require_super_admin()
    return success_response(CeleryMonitoringService.broker())


@handle_api_errors
@_gate
def history() -> tuple:
    """Recorded tasks, newest first, filtered and paged."""
    _require_super_admin()
    _require_history()
    return success_response(
        CeleryTaskHistoryService.list_tasks(
            state=request.args.get("state") or None,
            name=request.args.get("name") or None,
            worker=request.args.get("worker") or None,
            search=request.args.get("search") or None,
            window_hours=_int_arg("windowHours"),
            page=_int_arg("page", 1) or 1,
            per_page=_int_arg("perPage", 50) or 50,
            sort=request.args.get("sort") or None,
            order=request.args.get("order") or None,
        )
    )


@handle_api_errors
@_gate
def history_task(task_id: str) -> tuple:
    """One recorded task in full: result, exception and traceback included."""
    _require_super_admin()
    _require_history()
    return success_response(CeleryTaskHistoryService.get_task(task_id))


@handle_api_errors
@_gate
def task_types() -> tuple:
    """Outcome counts and runtimes per task type, plus registered types with no history yet."""
    _require_super_admin()
    window = _int_arg("windowHours", 24)
    stats = CeleryTaskHistoryService.task_types(window) if celery_task_history_enabled() else []
    seen = {row["name"] for row in stats}
    idle = [
        {
            "name": name,
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "retried": 0,
            "revoked": 0,
            "running": 0,
            "avgRuntimeSeconds": None,
            "maxRuntimeSeconds": None,
            "lastSeenAt": None,
        }
        for name in sorted(CeleryMonitoringService.registered_task_names() - seen)
    ]
    return success_response(
        {"results": sorted(stats + idle, key=lambda row: row["name"]), "windowHours": window}
    )


@handle_api_errors
@_gate
def control_revoke() -> tuple:
    actor = _require_super_admin()
    body = _body()
    return success_response(
        CeleryControlService.revoke(
            body.get("taskId"), terminate=bool(body.get("terminate")), signal=body.get("signal"), actor=actor
        )
    )


@handle_api_errors
@_gate
def control_rate_limit() -> tuple:
    actor = _require_super_admin()
    body = _body()
    return success_response(
        CeleryControlService.rate_limit(body.get("taskName"), body.get("rateLimit"), actor=actor, worker=body.get("worker"))
    )


@handle_api_errors
@_gate
def control_time_limit() -> tuple:
    actor = _require_super_admin()
    body = _body()
    return success_response(
        CeleryControlService.time_limit(
            body.get("taskName"), body.get("softSeconds"), body.get("hardSeconds"), actor=actor, worker=body.get("worker")
        )
    )


@handle_api_errors
@_gate
def control_worker(worker_name: str) -> tuple:
    actor = _require_super_admin()
    return success_response(CeleryControlService.worker_action(worker_name, _body(), actor=actor))
