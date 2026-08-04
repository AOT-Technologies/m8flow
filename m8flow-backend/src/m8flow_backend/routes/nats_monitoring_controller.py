"""Read-only NATS monitoring endpoints.

Two audiences, and the split matters:

- Broker-wide state (``/varz``, ``/jsz``) is **super-admin only**. JetStream reports it per
  account, not per tenant, and there is no honest way to filter it — a tenant-admin shown
  those numbers would be seeing every tenant's traffic.
- Event history comes from ``m8flow_nats_event_audit``, which carries a tenant per row, so
  a tenant-admin can safely be shown their own. Cross-tenant reads require super-admin and
  are requested explicitly via ``all_tenants``; they are never the default.

Message payload inspection is gated separately on
``M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED`` (off by default) because m8flow's streams retain
every payload indefinitely.
"""

from __future__ import annotations

from flask import g, request

from m8flow_backend.config import nats_message_inspection_enabled
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_backend.services.nats_event_audit_query_service import (
    NatsEventAuditQueryService,
)
from m8flow_backend.services.nats_monitoring_service import NatsMonitoringService
from m8flow_backend.tenancy import get_tenant_id
from spiffworkflow_backend.exceptions.api_error import ApiError


def _require_authenticated_user():
    user = getattr(g, "user", None)
    if not user:
        raise ApiError(
            error_code="not_authenticated",
            message="User not authenticated",
            status_code=401,
        )
    return user


def _is_super_admin() -> bool:
    """Whether this request is acting as a platform super-admin.

    Set by the tenant-resolution layer, the same signal tenant_scoping_patch uses to
    decide on RLS bypass.
    """
    return bool(getattr(g, "_m8flow_super_admin_request", False))


def _require_super_admin() -> None:
    _require_authenticated_user()
    if not _is_super_admin():
        raise ApiError(
            error_code="forbidden",
            message="Broker-wide NATS monitoring is restricted to super-admins.",
            status_code=403,
        )


def _active_tenant_id() -> str | None:
    try:
        return get_tenant_id()
    except RuntimeError:
        return None


def _audit_scope() -> tuple[str | None, bool]:
    """Resolve (tenant_id, all_tenants) for an event-history read.

    A super-admin may opt into a cross-tenant view with ``?allTenants=true``, or filter to
    one tenant with ``?tenantId=``. Everyone else is pinned to their active tenant, and
    ``all_tenants`` is never inferred.
    """
    _require_authenticated_user()

    if _is_super_admin():
        if str(request.args.get("allTenants", "")).lower() == "true":
            return None, True
        requested = request.args.get("tenantId")
        if requested:
            return requested, False
        return _active_tenant_id(), False

    return _active_tenant_id(), False


def _int_arg(name: str, default: int | None = None) -> int | None:
    raw = request.args.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ApiError(
            error_code="invalid_parameter",
            message=f"'{name}' must be an integer.",
            status_code=400,
        )


def _bool_arg(name: str) -> bool:
    return str(request.args.get(name, "")).lower() == "true"


@handle_api_errors
def overview() -> tuple:
    """Server health and throughput, plus JetStream totals."""
    _require_super_admin()
    return success_response(NatsMonitoringService.overview())


@handle_api_errors
def streams() -> tuple:
    """Streams and consumers with derived pending / lag / delivery figures."""
    _require_super_admin()
    return success_response(NatsMonitoringService.streams())


@handle_api_errors
def tenants() -> tuple:
    """Backlog and outcome counts per tenant."""
    _require_super_admin()
    return success_response({"results": NatsEventAuditQueryService.per_tenant()})


@handle_api_errors
def list_events() -> tuple:
    """Paged event history, scoped to the caller's tenant unless super-admin says otherwise."""
    tenant_id, all_tenants = _audit_scope()
    return success_response(
        NatsEventAuditQueryService.list_events(
            tenant_id=tenant_id,
            all_tenants=all_tenants,
            outcome=request.args.get("outcome"),
            process_identifier=request.args.get("processIdentifier"),
            username=request.args.get("username"),
            event_id=request.args.get("eventId"),
            worker=request.args.get("worker"),
            failures_only=_bool_arg("failuresOnly"),
            since_in_seconds=_int_arg("since"),
            until_in_seconds=_int_arg("until"),
            page=_int_arg("page", 1),
            per_page=_int_arg("perPage", 50),
        )
    )


@handle_api_errors
def events_summary() -> tuple:
    """Counts by outcome for the summary cards."""
    tenant_id, all_tenants = _audit_scope()
    return success_response(
        NatsEventAuditQueryService.summary(tenant_id=tenant_id, all_tenants=all_tenants)
    )


@handle_api_errors
def get_event(event_id: str) -> tuple:
    """One event's history, optionally with the payload still held in JetStream."""
    tenant_id, all_tenants = _audit_scope()
    event = NatsEventAuditQueryService.get_event(
        event_id, tenant_id=tenant_id, all_tenants=all_tenants
    )

    # The payload lives in NATS, not in the audit row: the row stores only a stream
    # sequence pointing at the single copy JetStream already retains.
    if _bool_arg("includePayload"):
        if not nats_message_inspection_enabled():
            raise ApiError(
                error_code="nats_message_inspection_disabled",
                message="Message payload inspection is disabled on this deployment.",
                status_code=403,
            )
        if not _is_super_admin():
            raise ApiError(
                error_code="forbidden",
                message="Message payload inspection is restricted to super-admins.",
                status_code=403,
            )
        stream_seq = event.get("streamSeq")
        if stream_seq:
            stream_name = request.args.get("streamName") or "M8FLOW_EVENTS"
            messages = NatsMonitoringService.get_messages(
                stream_name, start_seq=stream_seq, limit=1
            )
            event["payload"] = messages[0] if messages else None
        else:
            # No pointer recorded — e.g. the event never reached the stream.
            event["payload"] = None

    return success_response(event)


@handle_api_errors
def stream_messages(stream_name: str) -> tuple:
    """Browse raw messages in a stream by sequence. Never acknowledges them."""
    _require_super_admin()
    if not nats_message_inspection_enabled():
        raise ApiError(
            error_code="nats_message_inspection_disabled",
            message="Message payload inspection is disabled on this deployment.",
            status_code=403,
        )

    return success_response(
        {
            "results": NatsMonitoringService.get_messages(
                stream_name,
                start_seq=_int_arg("startSeq", 1),
                limit=_int_arg("limit", 10),
            )
        }
    )
