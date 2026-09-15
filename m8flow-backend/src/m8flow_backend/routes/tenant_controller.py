from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_backend.services.tenant_service import TenantService


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


@handle_api_errors
@require_permission(
    forbidden_message="Not allowed to view the tenant registry",
    group_fallback=False,
)
def get_tenant_by_id(tenant_id):
    tenant = TenantService.get_tenant_by_id(tenant_id)
    return success_response(_serialize_tenant(tenant), 200)


@handle_api_errors
@require_permission(
    forbidden_message="Not allowed to view the tenant registry",
    group_fallback=False,
)
def get_tenant_by_slug(slug):
    tenant = TenantService.get_tenant_by_slug(slug)
    return success_response(_serialize_tenant(tenant), 200)


@handle_api_errors
@require_permission(
    forbidden_message="Not allowed to view the tenant registry",
    group_fallback=False,
)
def get_all_tenants():
    tenants = TenantService.get_all_tenants()
    return success_response([_serialize_tenant(t) for t in tenants], 200)
