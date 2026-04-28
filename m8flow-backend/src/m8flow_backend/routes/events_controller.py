from __future__ import annotations

import logging

from flask import request
from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.helpers.response_helper import handle_api_errors, success_response

from m8flow_backend.services.nats_token_service import NatsTokenService

from m8flow_backend.services.nats_service import NatsService
from m8flow_backend.services.tenant_service import TenantService

logger = logging.getLogger("m8flow.events.controller")


def _resolve_tenant_and_validate_key() -> tuple[str, str, str]:
    """
    1. Extract X-M8FLOW-Tenant-Slug and X-M8FLOW-NATS-API-Key from headers.
    2. Resolve the slug to a tenant UUID via TenantService.
    3. Verify the API key against that tenant using NatsTokenService.verify_token.
    Returns (tenant_id, tenant_slug, api_key) on success; raises ApiError on failure.
    """
    tenant_slug = request.headers.get("X-M8FLOW-Tenant-Slug")
    api_key = request.headers.get("X-M8FLOW-NATS-API-Key")

    if not tenant_slug:
        logger.warning("m8flow-trigger: missing tenant slug header")
        raise ApiError(
            error_code="missing_tenant_slug",
            message="Required header X-M8FLOW-Tenant-Slug is missing.",
            status_code=400,
        )

    if not api_key:
        logger.warning("m8flow-trigger: missing API key header")
        raise ApiError(
            error_code="missing_api_key",
            message="Required header X-M8FLOW-NATS-API-Key is missing.",
            status_code=401,
        )

    # Step 1: Resolve slug → tenant UUID (TenantService handles 404 if not found)
    tenant = TenantService.get_tenant_by_slug(tenant_slug)
    tenant_id = tenant.id

    # Step 2: Verify the API key against the resolved tenant
    if not NatsTokenService.verify_token(tenant_id, api_key):
        logger.warning("m8flow-trigger: invalid API key for tenant slug=%s", tenant_slug)
        raise ApiError(
            error_code="invalid_api_key",
            message="The provided X-M8FLOW-NATS-API-Key is invalid for this tenant.",
            status_code=403,
        )

    return tenant_id, tenant_slug, api_key


@handle_api_errors
def m8flow_trigger() -> tuple:
    """
    POST /api/events/m8flow-trigger

    Receive an external trigger event, publish to NATS, and acknowledge.

    Required headers
    ----------------
    X-M8FLOW-NATS-API-Key : str
        A valid tenant API key generated via POST /api/nats-tokens.
    X-M8FLOW-Process-Identifier : str
        The identifier of the process to trigger.
    X-M8FLOW-Username : str
        The username on whose behalf the process is triggered.

    Request body (JSON)
    -------------------
    {
        "data": { ... }   # arbitrary caller-supplied payload
    }
    """
    tenant_id, tenant_slug, api_key = _resolve_tenant_and_validate_key()

    process_identifier = request.headers.get("X-M8FLOW-Process-Identifier")
    username = request.headers.get("X-M8FLOW-Username")
    provided_stream_name = request.headers.get("X-M8FLOW-Stream-Name")

    if not all([process_identifier, username, provided_stream_name]):
        raise ApiError(
            error_code="missing_required_headers",
            message="Required headers X-M8FLOW-Process-Identifier, X-M8FLOW-Username, and X-M8FLOW-Stream-Name are missing.",
            status_code=400,
        )

    body = request.get_json(silent=True) or {}
    data = body.get("data")

    # We use the provided_stream_name from the header for the NATS publish as requested.
    try:
        event_data = NatsService.publish_event(
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            process_identifier=process_identifier,
            username=username,
            payload=data,
            api_key=api_key,
            stream_name=provided_stream_name
        )

    except Exception as e:
        raise ApiError(
            error_code="nats_publish_failed",
            message=f"Failed to publish event to NATS: {str(e)}",
            status_code=500
        )

    # Pop internal fields so they don't show up in the event echo
    event_data.pop("api_key", None)
    event_data.pop("reply_to", None)
    event_data.pop("tenant_id", None)
    event_data.pop("tenant_slug", None)
    event_data.pop("username", None)
    
    # Process instance is returned separately
    process_instance_details = event_data.pop("process_instance", None)

    # Check if the consumer replied with an error
    if isinstance(process_instance_details, dict) and process_instance_details.get("error"):
        return success_response(
            {
                "ok": False,
                "message": "Event published but process instance creation failed.",
                "data": {
                    "tenant_id": tenant_id,
                    "tenant_slug": tenant_slug,
                    "process_identifier": process_identifier,
                    "username": username,
                    "event": event_data,
                    "error": process_instance_details.get("message", "Unknown error"),
                    "process_instance": None,
                },
            },
            422,
        )

    if process_instance_details is None:
        return success_response(
            {
                "ok": False,
                "message": "Event published but no response from consumer (timeout).",
                "data": {
                    "tenant_id": tenant_id,
                    "tenant_slug": tenant_slug,
                    "process_identifier": process_identifier,
                    "username": username,
                    "event": event_data,
                    "process_instance": None,
                },
            },
            202,
        )

    return success_response(
        {
            "ok": True,
            "message": "Event received and process instance created.",
            "data": {
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug,
                "process_identifier": process_identifier,
                "username": username,
                "event": event_data,
                "process_instance": process_instance_details,
            },
        },
        200,
    )



