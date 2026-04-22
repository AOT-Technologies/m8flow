from __future__ import annotations
from flask import g
from m8flow_backend.services.nats_token_service import NatsTokenService
from m8flow_backend.helpers.response_helper import success_response, handle_api_errors
from m8flow_backend.tenancy import get_tenant_id
from spiffworkflow_backend.exceptions.api_error import ApiError

def _serialize_nats_token(nats_token, raw_token=None):
    """Serialize NATS token model to dictionary. Uses raw_token if provided."""
    return {
        "token": raw_token if raw_token else "********",
        "tenantId": nats_token.m8f_tenant_id,
        "createdAtInSeconds": nats_token.created_at_in_seconds,
        "createdBy": nats_token.created_by,
        "updatedAtInSeconds": nats_token.updated_at_in_seconds,
        "modifiedBy": nats_token.modified_by
    }

def _require_authenticated_user():
    """Ensure user is authenticated."""
    user = getattr(g, 'user', None)
    if not user:
        raise ApiError(
            error_code="not_authenticated",
            message="User not authenticated",
            status_code=401
        )
    return user

@handle_api_errors
def generate_token():
    """
    Generate or regenerate a NATS token for the current tenant.
    
    Restricted to users with 'manage-nats-tokens' permission (tenant-admin, integrator).
    The permission check is performed by SpiffWorkflow's API security layer based on the
    operationId and URI defined in api.yml/m8flow.yml.
    """
    user = _require_authenticated_user()
    tenant_id = get_tenant_id()
    
    nats_token, raw_token = NatsTokenService.generate_token(
        tenant_id=tenant_id,
        user_id=user.username
    )
    
    return success_response(_serialize_nats_token(nats_token, raw_token), 201)
