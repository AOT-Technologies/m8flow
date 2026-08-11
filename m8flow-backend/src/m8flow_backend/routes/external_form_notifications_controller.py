"""Admin-facing view of external-form email notifications.

Gives tenant admins the two things the delivery path could previously only report to the
worker log: whether this tenant's SMTP secrets are usable at all, and what happened to each
individual notification. Also lets them requeue a request once the configuration is fixed.

Tenant scoping: for ordinary requests the tenant-scoping query listener
(services/tenant_scoping_patch) filters every SELECT, and nothing here may bypass it.
Super-admin requests are *exempt* from that listener, so each handler resolves an explicit
tenant filter from ?tenantId= and applies it itself — the same compensation
secrets_controller_patch and process_models_controller_patch already make.
"""

from __future__ import annotations

import flask.wrappers
from flask import jsonify, make_response
from flask import request as flask_request

from m8flow_backend.helpers.response_helper import error_response, handle_api_errors, success_response
from m8flow_backend.models.external_form_request import ExternalFormRequestModel
from m8flow_backend.models.external_form_request import ExternalFormRequestStatus
from m8flow_backend.services.external_form_notification_service import ExternalFormNotificationService
from m8flow_backend.tenancy import is_super_admin_request

# Guards against a caller asking for an unbounded page.
MAX_PER_PAGE = 200


def _requested_tenant_id() -> str | None:
    value = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")
    if isinstance(value, str):
        return value.strip() or None
    return None


def _explicit_tenant_filter() -> str | None:
    """Tenant to filter on, or None to rely on the ambient tenant-scoping listener.

    Only super-admin requests get an explicit filter: they are the ones the listener
    exempts. Honouring ?tenantId= for a normal user would let them name another tenant,
    but the listener still scopes them, so the extra filter could only ever narrow their
    own tenant to nothing — never widen it."""
    if not is_super_admin_request():
        return None
    return _requested_tenant_id()


def _tenant_name_map(tenant_ids: set[str]) -> dict[str, str]:
    if not tenant_ids:
        return {}
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

    tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
    return {tenant.id: tenant.name for tenant in tenants}


@handle_api_errors
def external_form_smtp_status() -> flask.wrappers.Response:
    """Whether the tenant can send external-form emails, and which NATS_SMTP_* secrets it
    still needs. Returns key names and flags only — never a value.

    A super admin must name the tenant: without one, the query would span every tenant and
    could report "configured" because some *other* tenant has SMTP set up."""
    tenant_id = _explicit_tenant_filter()
    if is_super_admin_request() and tenant_id is None:
        return error_response(
            "tenant_id_required",
            "Select a tenant to see its external form email configuration.",
            400,
        )
    status = ExternalFormNotificationService.smtp_configuration_status(tenant_id)
    return make_response(jsonify(status), 200)


@handle_api_errors
def external_form_notification_list(
    process_instance_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> flask.wrappers.Response:
    """Paginated notification tracking rows for the active tenant, newest first.

    Rows are serialized with to_admin_dict(), which deliberately omits reference_id: that
    token is the credential in the recipient's emailed link. Recipient email addresses are
    included, so a super admin querying across tenants gets each row labelled with its
    owning tenant rather than an unattributed mix."""
    per_page = max(1, min(int(per_page), MAX_PER_PAGE))
    tenant_id = _explicit_tenant_filter()

    query = ExternalFormRequestModel.query
    if tenant_id is not None:
        query = query.filter(ExternalFormRequestModel.m8f_tenant_id == tenant_id)
    if process_instance_id is not None:
        query = query.filter(ExternalFormRequestModel.process_instance_id == process_instance_id)
    if status:
        query = query.filter(ExternalFormRequestModel.status == status)

    results = query.order_by(ExternalFormRequestModel.created_at_in_seconds.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    rows = [row.to_admin_dict() for row in results.items]
    if is_super_admin_request():
        tenant_ids = {row.m8f_tenant_id for row in results.items if row.m8f_tenant_id}
        name_by_id = _tenant_name_map(tenant_ids)
        for payload, row in zip(rows, results.items):
            payload["tenantId"] = row.m8f_tenant_id
            payload["tenantName"] = name_by_id.get(row.m8f_tenant_id)

    return make_response(
        jsonify(
            {
                "results": rows,
                "pagination": {
                    "count": len(results.items),
                    "total": results.total,
                    "pages": results.pages,
                },
            }
        ),
        200,
    )


@handle_api_errors
def external_form_notification_resend(request_id: int) -> flask.wrappers.Response:
    """Requeue one notification for delivery.

    Applies to requests parked as smtp_unconfigured and to sends that failed and were
    released for retry. The notification worker's sweep picks the row up on its next pass
    (M8FLOW_NOTIFICATION_SWEEP_INTERVAL_SECONDS), so delivery is not instantaneous.

    A super admin must name the tenant: request_id is a bare integer, so without a filter
    it would address any tenant's row."""
    tenant_id = _explicit_tenant_filter()
    if is_super_admin_request() and tenant_id is None:
        return error_response(
            "tenant_id_required",
            "Select a tenant before resending one of its notifications.",
            400,
        )

    query = ExternalFormRequestModel.query.filter(ExternalFormRequestModel.id == request_id)
    if tenant_id is not None:
        query = query.filter(ExternalFormRequestModel.m8f_tenant_id == tenant_id)
    row = query.first()
    if row is None:
        return error_response(
            "external_form_request_not_found",
            "No external form notification exists with that id for this tenant.",
            404,
        )

    if not ExternalFormNotificationService.requeue(request_id, tenant_id=tenant_id):
        return error_response(
            "external_form_request_not_resendable",
            (
                f"A notification in status '{row.status}' cannot be resent. Only requests"
                " awaiting delivery, parked for missing SMTP configuration, or whose send"
                " failed can be requeued."
            ),
            409,
        )

    return success_response(
        {
            "ok": True,
            "id": request_id,
            "status": ExternalFormRequestStatus.pending.value,
            "message": "Notification requeued; the worker will retry it on its next sweep.",
        },
        200,
    )
