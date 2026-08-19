from __future__ import annotations

from m8flow_backend.helpers.response_helper import handle_api_errors, success_response


@handle_api_errors
def notification_smtp_status() -> tuple:
    """Return which NATS_SMTP_* secret keys are configured for the active tenant.

    The response carries only per-key presence booleans and the overall
    ``configured`` flag — secret values are never included. The frontend uses
    this to surface a warning banner when the required SMTP secrets are missing.
    """
    from m8flow_backend.services.external_form_notification_service import (
        ExternalFormNotificationService,
    )

    status = ExternalFormNotificationService.check_smtp_configured()
    return success_response(status, 200)
