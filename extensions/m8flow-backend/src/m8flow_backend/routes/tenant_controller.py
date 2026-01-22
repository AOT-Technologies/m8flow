from flask import g
from spiffworkflow_backend.services.authorization_service import AuthorizationService
from spiffworkflow_backend.exceptions.api_error import ApiError
from m8flow_backend.services.tenant_service import TenantService
from m8flow_backend.helpers.response_helper import success_response, handle_api_errors
import uuid

def _serialize_tenant(tenant):
    """Serialize tenant model to camelCase dictionary."""
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "createdAt": tenant.created.isoformat() if tenant.created else None,
        "modifiedAt": tenant.modified.isoformat() if tenant.modified else None,
        "createdBy": tenant.created_by,
        "modifiedBy": tenant.modified_by
    }

def _check_admin_permission():
    """Check if user has admin permission to manage tenants."""
    if not hasattr(g, "user") or not g.user:
        raise ApiError(error_code="not_authenticated", message="User not authenticated", status_code=401)
    
    # TODO: This logic may change to role-based permissions in the future. Ensure to update this accordingly.
    has_permission = AuthorizationService.user_has_permission(
        user=g.user,
        permission="create",
        target_uri="/admin/tenants"
    )
    
    if not has_permission:
        raise ApiError(
            error_code="insufficient_permissions",
            message="User does not have sufficient permissions to manage tenants. Admin or system role required.",
            status_code=403
        )

@handle_api_errors
def create_tenant(body):
    _check_admin_permission()

    tenant_id = body.get('id', str(uuid.uuid4()))
    name = body.get('name')
    slug = body.get('slug')
    status_str = "ACTIVE"

    tenant = TenantService.create_tenant(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        status_str=status_str,
        user_id=g.user.username
    )
    
    return success_response(_serialize_tenant(tenant), 201)


@handle_api_errors
def get_tenant_by_id(tenant_id):
    """Fetch tenant by ID."""
    _check_admin_permission()
    tenant = TenantService.get_tenant_by_id(tenant_id)
    return success_response(_serialize_tenant(tenant), 200)


@handle_api_errors
def get_tenant_by_slug(slug):
    """Fetch tenant by slug."""
    _check_admin_permission()
    tenant = TenantService.get_tenant_by_slug(slug)
    return success_response(_serialize_tenant(tenant), 200)


@handle_api_errors
def get_all_tenants():
    """Fetch all tenants, excluding the default tenant."""
    _check_admin_permission()
    tenants = TenantService.get_all_tenants()
    return success_response([_serialize_tenant(t) for t in tenants], 200)

@handle_api_errors
def delete_tenant(tenant_id):
    """Soft delete a tenant by setting status to DELETED."""
    _check_admin_permission()
    tenant = TenantService.delete_tenant(tenant_id, g.user.username)
    
    return success_response({
        "message": f"Tenant '{tenant.name}' has been successfully deleted."
    }, 200)

@handle_api_errors
def update_tenant(tenant_id, body):
    """Update tenant name and status. Slug cannot be updated."""
    _check_admin_permission()
    
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
        user_id=g.user.username
    )
    
    return success_response({
        "message": f"Tenant '{tenant.name}' has been successfully updated.",
        "tenant": _serialize_tenant(tenant)
    }, 200)
