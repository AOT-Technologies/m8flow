from __future__ import annotations

from flask import request

from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_backend.services.external_form_service import ExternalFormService


@handle_api_errors
def external_form_show(reference_id: str) -> tuple:
    """Public lookup for a secure link; ``actionable`` is false when the link is
    expired, superseded, or already submitted."""
    context = ExternalFormService.get_form_context(reference_id)
    return success_response(context, 200)


@handle_api_errors
def external_form_submit(reference_id: str) -> tuple:
    """Public submission callback: stores the data and resumes the workflow as the
    recipient user. Only the first valid submission for a task counts."""
    body = request.get_json(silent=True) or {}
    form_data = body.get("data", body)
    if not isinstance(form_data, dict):
        form_data = {"value": form_data}

    result = ExternalFormService.submit(reference_id, form_data)
    return success_response(
        {
            "ok": True,
            "message": "Form submission accepted; the workflow has continued.",
            "data": result,
        },
        200,
    )


# Tenant comes from the tracked row, so middleware must not resolve it from auth data.
external_form_show._m8flow_sets_tenant_context = True  # type: ignore[attr-defined]
external_form_submit._m8flow_sets_tenant_context = True  # type: ignore[attr-defined]
