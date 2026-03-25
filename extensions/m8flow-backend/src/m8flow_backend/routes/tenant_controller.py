from flask import g
from spiffworkflow_backend.exceptions.api_error import ApiError
from m8flow_backend.services.tenant_service import TenantService
from m8flow_backend.helpers.response_helper import success_response, handle_api_errors


def _serialize_tenant(tenant):
    """Serialize tenant model to Spiff-standard (camelCase) dictionary."""
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "createdBy": tenant.created_by,
        "modifiedBy": tenant.modified_by,
        "createdAtInSeconds": tenant.created_at_in_seconds,
        "updatedAtInSeconds": tenant.updated_at_in_seconds,
    }

@handle_api_errors
def check_tenant_exists(identifier: str):
    """
    Check if an active tenant exists by slug or id. Unauthenticated; for pre-login tenant selection.
    Returns {"exists": true, "tenant_id": "..."} or {"exists": false}.
    """
    result = TenantService.check_tenant_exists(identifier or "")
    return success_response(result, 200)


def _require_authenticated_user():
    """Check if user is authenticated and return user, or raise ApiError."""
    user = getattr(g, 'user', None)
    if not user:
        raise ApiError(
            error_code="not_authenticated",
            message="User not authenticated",
            status_code=401
        )
    return user


@handle_api_errors
def get_tenant_by_id(tenant_id):
    """Fetch tenant by ID."""
    tenant = TenantService.get_tenant_by_id(tenant_id)
    return success_response(_serialize_tenant(tenant), 200)


@handle_api_errors
def get_tenant_by_slug(slug):
    """Fetch tenant by slug."""
    tenant = TenantService.get_tenant_by_slug(slug)
    return success_response(_serialize_tenant(tenant), 200)


@handle_api_errors
def get_all_tenants():
    """Fetch all tenants, excluding the default tenant."""
    tenants = TenantService.get_all_tenants()
    return success_response([_serialize_tenant(t) for t in tenants], 200)

