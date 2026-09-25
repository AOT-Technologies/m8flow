"""Read-only NATS monitoring endpoints. Super-admin only.

Every endpoint is gated by ``@require_permission`` against the ``/m8flow/nats/*`` grant in
``config/permissions/m8flow.yml`` (super-admin only, no group fallback). On top of that:

- Broker-wide state (``/varz``, ``/jsz``) and raw stream browsing are reported per NATS
  account, not per tenant, so those handlers additionally require super-admin outright.
- Event history comes from ``m8flow_nats_event_audit``, which carries a tenant per row.
  ``_audit_scope`` pins a non-super-admin caller to their active tenant, so the scoping
  stays correct should the YAML grant ever be widened; a super-admin may ask for
  ``allTenants`` or a specific ``tenantId``.

Payload inspection is additionally gated on ``M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED``
(off by default) because m8flow's streams retain every payload indefinitely.
"""

from __future__ import annotations

from flask import request

from m8flow_backend.auth import is_super_admin_request, require_current_user
from m8flow_backend.auth.canonicalize import current_tenant_id_or_none
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.config import (
    TRUTHY,
    nats_message_inspection_enabled,
)
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_backend.services.nats_event_audit_query_service import NatsEventAuditQueryService, stream_for_worker
from m8flow_backend.services.nats_monitoring_service import NatsMonitoringService

# YAML is the only grant: the editor/tenant-admin identifier fallback must not open these.
_gate = require_permission(group_fallback=False)


def _require_super_admin() -> None:
    require_current_user()
    if not is_super_admin_request():
        raise ApiError(
            error_code="forbidden",
            message="Broker-wide NATS monitoring is restricted to super-admins.",
            status_code=403,
        )


def _bool_arg(name: str) -> bool:
    """Same vocabulary as the env flags; anything unrecognised is false, so a typo scopes
    the request *down* rather than widening it."""
    return str(request.args.get(name, "")).strip().lower() in TRUTHY


def _audit_scope() -> tuple[str | None, bool]:
    """Resolve (tenant_id, all_tenants) for an event-history read.

    A super-admin may opt into a cross-tenant view with ``?allTenants=true`` or filter to
    one tenant with ``?tenantId=``. Everyone else is pinned to their active tenant, and
    ``all_tenants`` is never inferred.
    """
    require_current_user()
    if is_super_admin_request():
        if _bool_arg("allTenants"):
            return None, True
        requested = (request.args.get("tenantId") or "").strip()
        if requested:
            return requested, False
    return current_tenant_id_or_none(), False


def _int_arg(name: str, default: int | None = None) -> int | None:
    raw = request.args.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ApiError(error_code="invalid_parameter", message=f"'{name}' must be an integer.", status_code=400)


def _require_inspection_enabled() -> None:
    if not nats_message_inspection_enabled():
        raise ApiError(
            error_code="nats_message_inspection_disabled",
            message="Message payload inspection is disabled on this deployment.",
            status_code=403,
        )


@handle_api_errors
@_gate
def overview() -> tuple:
    """Server health and throughput, plus JetStream totals."""
    _require_super_admin()
    return success_response(NatsMonitoringService.overview())


@handle_api_errors
@_gate
def streams() -> tuple:
    """Streams and consumers with derived pending / lag / delivery figures."""
    _require_super_admin()
    return success_response(NatsMonitoringService.streams())


@handle_api_errors
@_gate
def tenants() -> tuple:
    """Backlog and outcome counts per tenant."""
    _require_super_admin()
    return success_response({"results": NatsEventAuditQueryService.per_tenant()})


@handle_api_errors
@_gate
def list_events() -> tuple:
    """Paged event history.

    Also reports whether payload inspection is enabled, so clients (including
    tenant-admins, who cannot read the broker overview) can omit a payload action that
    would predictably fail with nats_message_inspection_disabled."""
    tenant_id, all_tenants = _audit_scope()
    page = NatsEventAuditQueryService.list_events(
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
    return success_response({**page, "messageInspectionEnabled": nats_message_inspection_enabled()})


@handle_api_errors
@_gate
def events_summary() -> tuple:
    """Counts by outcome for the summary cards."""
    tenant_id, all_tenants = _audit_scope()
    return success_response(NatsEventAuditQueryService.summary(tenant_id=tenant_id, all_tenants=all_tenants))


@handle_api_errors
@_gate
def get_event(event_id: str) -> tuple:
    """One event's history, optionally with the payload still held in JetStream."""
    tenant_id, all_tenants = _audit_scope()
    event = NatsEventAuditQueryService.get_event(event_id, tenant_id=tenant_id, all_tenants=all_tenants)

    if _bool_arg("includePayload"):
        _require_inspection_enabled()
        # Both halves of the JetStream pointer come from the already-scoped row.
        stream_seq = event.get("streamSeq")
        if stream_seq:
            messages = NatsMonitoringService.get_messages(
                stream_for_worker(event.get("worker")), start_seq=stream_seq, limit=1
            )
            event["payload"] = messages[0] if messages else None
        else:
            event["payload"] = None

    return success_response(event)


@handle_api_errors
@_gate
def stream_messages(stream_name: str) -> tuple:
    """Browse raw messages in a stream by sequence. Never acknowledges them."""
    _require_super_admin()
    _require_inspection_enabled()
    return success_response(
        {
            "results": NatsMonitoringService.get_messages(
                stream_name,
                start_seq=_int_arg("startSeq", 1),
                limit=_int_arg("limit", 10),
            )
        }
    )
