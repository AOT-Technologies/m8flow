"""Admin-facing view of external-form email notifications.

Gives tenant admins the two things the delivery path could otherwise only report to the
worker log: whether this tenant's SMTP secrets are usable at all, and what happened to
each individual notification. Also lets them requeue a request once the configuration is
fixed.

Every handler resolves one concrete tenant with `require_tenant_id` and filters on it
explicitly, so none of them can read or write another tenant's row -- including a
super-admin, whose bare numeric `request_id` would otherwise address any tenant.

Authorization reuses the tenant's *secrets* permission rather than a URI of its own.
Two reasons, and the second is decisive:

* It is the right audience. External-form delivery is configured entirely by the
  tenant's NATS_SMTP_* secrets, so whoever may read or repair that configuration is
  exactly who should see delivery status and press resend.
* A new grant would never take effect. `identity.import_yaml` seeds a tenant once
  (guarded by `tenant_yaml_grants_present`), so a permission added to m8flow.yml after
  a tenant was seeded never materializes for it -- these routes would answer 403 for
  every existing tenant until someone reassigned a tenant role.

`group_fallback=False` on every handler, so the materialized grant is the only way in:
the fallback would otherwise open every path to any tenant-admin or editor, and these
responses carry recipient email addresses.
"""

from __future__ import annotations

from typing import Any

import flask.wrappers
from flask import g, jsonify, make_response
from flask import request as flask_request

from m8flow_backend.auth import require_current_user, require_tenant_id
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors
from m8flow_backend.models.external_form_request import ExternalFormRequestModel
from m8flow_backend.models.external_form_request import ExternalFormRequestStatus
from m8flow_backend.services.external_form_notification_service import (
    ExternalFormNotificationService,
)

# The permission that governs this tenant's external-form mail configuration: its
# NATS_SMTP_* secrets. See the module docstring for why these routes authorize against
# it instead of a URI of their own. `read` (GET) reaches tenant-admin, integrator,
# viewer and super-admin; `create` (the POST resend) reaches tenant-admin, integrator
# and super-admin -- see the secrets grants in config/permissions/m8flow.yml.
SMTP_CONFIG_PERMISSION_URI = "/secrets"

# Guards against a caller asking for an unbounded page.
MAX_PER_PAGE = 200


def _int_arg(name: str, default: int) -> int:
    raw = flask_request.args.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ApiError("invalid_parameter", f"'{name}' must be an integer.", 400) from None


@handle_api_errors
@require_permission(
    uri=SMTP_CONFIG_PERMISSION_URI,
    forbidden_message="Not allowed to read external form notifications",
    group_fallback=False,
)
def external_form_smtp_status() -> flask.wrappers.Response:
    """Whether the tenant can send external-form emails, and which NATS_SMTP_* secrets it
    still needs. Returns key names and flags only -- never a value.

    A tenant must be selected: without one the answer would either span tenants or be
    meaningless, and reporting "configured" because some *other* tenant has SMTP set up
    is worse than refusing."""
    user = require_current_user()
    tenant_id = require_tenant_id(user)
    status = ExternalFormNotificationService.smtp_configuration_status(tenant_id)
    return make_response(jsonify(status), 200)


@handle_api_errors
@require_permission(
    uri=SMTP_CONFIG_PERMISSION_URI,
    forbidden_message="Not allowed to read external form notifications",
    group_fallback=False,
)
def external_form_notification_list() -> flask.wrappers.Response:
    """Paginated notification tracking rows for the active tenant, newest first.

    Rows are serialized with to_admin_dict(), which deliberately omits reference_id: that
    token is the credential in the recipient's emailed link."""
    user = require_current_user()
    tenant_id = require_tenant_id(user)
    page = max(1, _int_arg("page", 1))
    per_page = max(1, min(_int_arg("per_page", 50), MAX_PER_PAGE))
    process_instance_id = _int_arg("process_instance_id", 0)
    status = (flask_request.args.get("status") or "").strip() or None

    query = g.db_session.query(ExternalFormRequestModel).filter(
        ExternalFormRequestModel.m8f_tenant_id == tenant_id
    )
    if process_instance_id:
        query = query.filter(ExternalFormRequestModel.process_instance_id == process_instance_id)
    if status:
        query = query.filter(ExternalFormRequestModel.status == status)

    total = query.count()
    rows = (
        query.order_by(
            ExternalFormRequestModel.created_at_in_seconds.desc(),
            ExternalFormRequestModel.id.desc(),
        )
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )

    results: list[dict[str, Any]] = [row.to_admin_dict() for row in rows]
    pages = (total + per_page - 1) // per_page
    return make_response(
        jsonify(
            {
                "results": results,
                "pagination": {"count": len(results), "total": total, "pages": pages, "page": page},
            }
        ),
        200,
    )


@handle_api_errors
@require_permission(
    uri=SMTP_CONFIG_PERMISSION_URI,
    forbidden_message="Not allowed to resend external form notifications",
    group_fallback=False,
)
def external_form_notification_resend(request_id: int) -> flask.wrappers.Response:
    """Requeue one notification for delivery.

    Applies to requests parked as smtp_unconfigured and to sends that failed and were
    released for retry. The notification worker's sweep picks the row up on its next pass
    (M8FLOW_NOTIFICATION_SWEEP_INTERVAL_SECONDS), so delivery is not instantaneous.

    A tenant must be selected: request_id is a bare integer, so without a filter it would
    address any tenant's row."""
    user = require_current_user()
    tenant_id = require_tenant_id(user)

    row = (
        g.db_session.query(ExternalFormRequestModel)
        .filter(
            ExternalFormRequestModel.id == int(request_id),
            ExternalFormRequestModel.m8f_tenant_id == tenant_id,
        )
        .first()
    )
    if row is None:
        raise ApiError(
            "external_form_request_not_found",
            "No external form notification exists with that id for this tenant.",
            404,
        )

    if not ExternalFormNotificationService.requeue(int(request_id), tenant_id=tenant_id):
        raise ApiError(
            "external_form_request_not_resendable",
            (
                f"A notification in status '{row.status}' cannot be resent. Only requests"
                " awaiting delivery, parked for missing SMTP configuration, or whose send"
                " failed can be requeued."
            ),
            409,
        )

    return make_response(
        jsonify(
            {
                "ok": True,
                "id": int(request_id),
                "status": ExternalFormRequestStatus.pending.value,
                "message": "Notification requeued; the worker will retry it on its next sweep.",
            }
        ),
        200,
    )
