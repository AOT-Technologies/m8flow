from sqlalchemy.exc import IntegrityError
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
    def create_tenant(tenant_id: str, name: str, slug: str, status_str: str, user_id: str):
        if not name:
             raise ApiError(error_code="missing_name", message="Name is required", status_code=400)
        if not slug:
             raise ApiError(error_code="missing_slug", message="Slug is required", status_code=400)
        
        # Check if ID already exists
        existing_id = M8flowTenantModel.query.filter_by(id=tenant_id).first()
        if existing_id:
            raise ApiError(
                error_code="tenant_id_exists", 
                message=f"Tenant with ID '{tenant_id}' already exists.", 
                status_code=409
            )

        existing_slug = M8flowTenantModel.query.filter_by(slug=slug).first()
        if existing_slug:
            raise ApiError(
                error_code="tenant_slug_exists", 
                message=f"Tenant with slug '{slug}' already exists.", 
                status_code=409
            )

        tenant = M8flowTenantModel(
            id=tenant_id,
            name=name,
            slug=slug,
            status=TenantStatus(status_str),
            created_by=user_id,
            modified_by=user_id
        )
        
        try:
            db.session.add(tenant)
            db.session.commit()
            return tenant
        except IntegrityError:
            db.session.rollback()
            raise ApiError(
                error_code="tenant_conflict", 
                message="A tenant with this ID or slug already exists.", 
                status_code=409
            )
        except Exception as e:
            db.session.rollback()
            raise ApiError(
                error_code="database_error",
                message=str(e),
                status_code=500
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

    @staticmethod
    def delete_tenant(tenant_id: str, user_id: str):
        TenantService._check_not_default_tenant(tenant_id)
        
        tenant = M8flowTenantModel.query.filter_by(id=tenant_id).first()
        
        if not tenant:
            raise ApiError(
                error_code="tenant_not_found",
                message=f"Tenant with ID '{tenant_id}' not found.",
                status_code=404
            )
        
        if tenant.status == TenantStatus.DELETED:
            raise ApiError(
                error_code="tenant_already_deleted",
                message=f"Tenant with ID '{tenant_id}' is already deleted.",
                status_code=400
            )
        
        try:
            tenant.status = TenantStatus.DELETED
            tenant.modified_by = user_id
            
            db.session.commit()
            return tenant
        except Exception as e:
            db.session.rollback()
            raise ApiError(
                error_code="database_error",
                message=f"Error deleting tenant: {str(e)}",
                status_code=500
            )

    @staticmethod
    def update_tenant(tenant_id: str, name: str | None, status_str: str | None, user_id: str):
        TenantService._check_not_default_tenant(tenant_id)
        
        tenant = M8flowTenantModel.query.filter_by(id=tenant_id).first()
        
        if not tenant:
            raise ApiError(
                error_code="tenant_not_found",
                message=f"Tenant with ID '{tenant_id}' not found.",
                status_code=404
            )
        
        if tenant.status == TenantStatus.DELETED:
            raise ApiError(
                error_code="tenant_deleted",
                message=f"Cannot update tenant with ID '{tenant_id}' because it is deleted.",
                status_code=400
            )

        try:
            if name:
                tenant.name = name
            
            if status_str:
                try:
                    tenant.status = TenantStatus(status_str)
                except ValueError:
                    raise ApiError(
                        error_code="invalid_status",
                        message=f"Invalid status value: '{status_str}'. Must be one of: ACTIVE, INACTIVE, DELETED.",
                        status_code=400
                    )
            
            tenant.modified_by = user_id
            db.session.commit()
            return tenant
        except ApiError:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            raise ApiError(
                error_code="database_error",
                message=f"Error updating tenant: {str(e)}",
                status_code=500
            )
