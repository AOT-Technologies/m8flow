from flask import g
from spiffworkflow_backend.exceptions.api_error import ApiError
from m8flow_backend.services.tenant_service import TenantService
from m8flow_backend.helpers.response_helper import success_response, handle_api_errors
import uuid


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
def create_tenant(body):
    user = _require_authenticated_user()
    body = body or {}

    tenant_id = body.get('id', str(uuid.uuid4()))
    name = body.get('name')
    slug = body.get('slug')
    status_str = "ACTIVE"

    tenant = TenantService.create_tenant(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        status_str=status_str,
        user_id=user.username
    )
    
    return success_response(_serialize_tenant(tenant), 201)


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

@handle_api_errors
def delete_tenant(tenant_id):
    """Soft delete a tenant by setting status to DELETED."""
    user = _require_authenticated_user()
    tenant = TenantService.delete_tenant(tenant_id, user.username)
    
    return success_response({
        "message": f"Tenant '{tenant.name}' has been successfully deleted."
    }, 200)

@handle_api_errors
def update_tenant(tenant_id, body):
    """Update tenant name and status. Slug cannot be updated."""
    user = _require_authenticated_user()
    body = body or {}

    if 'slug' in body: 
        raise ApiError(
            error_code="slug_update_forbidden",
            message="Slug cannot be updated. It is immutable after creation.",
            status_code=400
        )

    tenant = TenantService.update_tenant(
        tenant_id=tenant_id,
        name=body.get('name'),
        status_str=body.get('status'),
        user_id=user.username
    )
    
    return success_response({
        "message": f"Tenant '{tenant.name}' has been successfully updated."
    }, 200)
