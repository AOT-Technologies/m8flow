from __future__ import annotations

import logging
from flask import g, request
from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.config import nats_events_stream_name
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response

from m8flow_backend.services.nats_token_service import AuthenticatedKey, NatsTokenService

from m8flow_backend.services.nats_service import NatsService
from m8flow_backend.services.tenant_identity_helpers import tenant_slug_for_identifier
from m8flow_backend.tenancy import get_context_tenant_id, set_context_tenant_id

logger = logging.getLogger("m8flow.events.controller")


def _set_validated_tenant_context(tenant_id: str) -> None:
    g.m8flow_tenant_id = tenant_id
    if get_context_tenant_id() != tenant_id:
        g._m8flow_ctx_token = set_context_tenant_id(tenant_id)


def _authenticate_api_key() -> AuthenticatedKey:
    """
    Authenticate the caller purely from the X-M8FLOW-NATS-API-Key header.

    The key alone resolves the tenant, the owning identity, and the key's scope;
    no JWT is required for this machine-to-machine trigger endpoint.

    Returns the resolved identity; raises ApiError (401/403) on failure.
    """
    api_key = request.headers.get("X-M8FLOW-NATS-API-Key")
    if not api_key:
        logger.warning("m8flow-trigger: missing API key header")
        raise ApiError(
            error_code="missing_api_key",
            message="Required header X-M8FLOW-NATS-API-Key is missing.",
            status_code=401,
        )

    authenticated = NatsTokenService.authenticate_key(api_key)
    if authenticated is None:
        logger.warning("m8flow-trigger: invalid, expired, or revoked API key")
        raise ApiError(
            error_code="invalid_api_key",
            message="The provided X-M8FLOW-NATS-API-Key is invalid, expired, or revoked.",
            status_code=403,
        )

    return authenticated


def _process_identifier_from_request(body: dict) -> str:
    """Resolve the process identifier from the JSON body, falling back to the
    deprecated X-M8FLOW-Process-Identifier header for backwards compatibility."""
    process_identifier = body.get("processIdentifier")
    if not isinstance(process_identifier, str) or not process_identifier.strip():
        process_identifier = request.headers.get("X-M8FLOW-Process-Identifier")

    if not isinstance(process_identifier, str) or not process_identifier.strip():
        raise ApiError(
            error_code="missing_process_identifier",
            message="A processIdentifier is required in the request body.",
            status_code=400,
        )
    return process_identifier.strip()


@handle_api_errors
def m8flow_trigger() -> tuple:
    """
    POST /api/events/m8flow-trigger

    Receive an external trigger event, publish to NATS, and acknowledge.

    Authentication / identity
    -------------------------
    X-M8FLOW-NATS-API-Key : str
        A valid tenant API key generated via POST /api/nats-tokens. The key alone
        authenticates the caller: the tenant, the owning identity, and the key's
        scope are all derived from it. No JWT is required.

    Request body (JSON)
    -------------------
    {
        "processIdentifier": "group/process",  # which process to trigger
        "data": { ... }                        # arbitrary caller-supplied payload
    }

    ``processIdentifier`` may also be supplied via the deprecated
    X-M8FLOW-Process-Identifier header for backwards compatibility.
    """
    authenticated = _authenticate_api_key()
    tenant_id = authenticated.tenant_id

    tenant_slug = tenant_slug_for_identifier(tenant_id)
    if not tenant_slug:
        logger.warning("m8flow-trigger: unable to resolve tenant slug for tenant=%s", tenant_id)
        raise ApiError(
            error_code="tenant_slug_unresolved",
            message="Could not resolve the tenant slug for the API key's tenant.",
            status_code=400,
        )

    username = authenticated.created_by
    _set_validated_tenant_context(tenant_id)

    body = request.get_json(silent=True) or {}
    process_identifier = _process_identifier_from_request(body)

    # Enforce the key's scope: a scoped key may only trigger its allowed processes.
    if not NatsTokenService.scope_allows(authenticated.scope, process_identifier):
        logger.warning(
            "m8flow-trigger: key %s not scoped for process %s",
            authenticated.key_id,
            process_identifier,
        )
        raise ApiError(
            error_code="process_not_in_scope",
            message="This API key is not authorized to trigger the requested process.",
            status_code=403,
        )

    data = body.get("data")
    provided_stream_name = nats_events_stream_name()
    # Forward the validated raw key to the consumer, preserving existing downstream behavior.
    raw_api_key = request.headers.get("X-M8FLOW-NATS-API-Key")

    try:
        event_data = NatsService.publish_event(
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            process_identifier=process_identifier,
            username=username,
            payload=data,
            api_key=raw_api_key,
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


m8flow_trigger._m8flow_sets_tenant_context = True  # type: ignore[attr-defined]
