from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.exceptions.api_error import ApiError

class TenantService:
    @staticmethod
    def _check_not_default_tenant(identifier: str):
        """Check that the given identifier is not 'default' to prevent operations on default tenant."""
        if identifier and identifier.lower() == "default":
            raise ApiError(
                error_code="forbidden_tenant",
                message="Cannot perform operations on default tenant.",
                status_code=403
            )

    @staticmethod
    def get_tenant_by_id(tenant_id: str):
        TenantService._check_not_default_tenant(tenant_id)
        
        tenant = M8flowTenantModel.query.filter_by(id=tenant_id).first()
        
        if not tenant:
            raise ApiError(
                error_code="tenant_not_found",
                message=f"Tenant with ID '{tenant_id}' not found.",
                status_code=404
            )
        return tenant

    @staticmethod
    def check_tenant_exists(identifier: str) -> dict:
        """
        Check if an active tenant exists by slug or id. Unauthenticated; for pre-login tenant selection.
        Returns {"exists": True, "tenant_id": "..."} or {"exists": False}. Only considers ACTIVE tenants.
        """
        if not identifier or not identifier.strip():
            return {"exists": False}
        identifier = identifier.strip()
        tenant = (
            M8flowTenantModel.query.filter(
                M8flowTenantModel.status == TenantStatus.ACTIVE,
                db.or_(
                    M8flowTenantModel.slug == identifier,
                    M8flowTenantModel.id == identifier,
                ),
            )
            .first()
        )
        if tenant:
            return {"exists": True, "tenant_id": tenant.id}
        return {"exists": False}

    @staticmethod
    def get_tenant_by_slug(slug: str):
        TenantService._check_not_default_tenant(slug)
        
        tenant = M8flowTenantModel.query.filter_by(slug=slug).first()
        if not tenant:
            raise ApiError(
                error_code="tenant_not_found",
                message=f"Tenant with slug '{slug}' not found.",
                status_code=404
            )
        return tenant

    @staticmethod
    def get_all_tenants():
        try:
            return M8flowTenantModel.query.filter(
                M8flowTenantModel.id != "default",
                M8flowTenantModel.slug != "default"
            ).all()
        except Exception as e:
            raise ApiError(
                error_code="database_error",
                message=f"Error fetching tenants: {str(e)}",
                status_code=500
            )

