from flask import jsonify, make_response, g, current_app
from sqlalchemy.exc import IntegrityError
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.authorization_service import AuthorizationService
import uuid

def _check_admin_permission():
    """Check if user has admin permission to manage tenants."""
    if not hasattr(g, "user") or not g.user:
        raise ApiError(error_code="not_authenticated", message="User not authenticated", status_code=401)
    
    # Check if user has permission to manage tenants (admin/system role)
    has_permission = AuthorizationService.user_has_permission(
        user=g.user,
        permission="create",  # Using 'create' as admin permission check
        target_uri="/admin/tenants"
    )
    
    if not has_permission:
        raise ApiError(
            error_code="insufficient_permissions",
            message="User does not have sufficient permissions to manage tenants. Admin or system role required.",
            status_code=403
        )

def _check_not_default_tenant(identifier: str, identifier_type: str = "tenant"):
    """Check that the given identifier is not 'default' to prevent operations on default tenant.
    
    Args:
        identifier: The tenant ID or slug to check
        identifier_type: Type of identifier for error message (e.g., 'tenant', 'ID', 'slug')
    """
    if identifier and identifier.lower() == "default":
        raise ApiError(
            error_code="forbidden_tenant",
            message=f"Cannot perform operations on default {identifier_type}.",
            status_code=403
        )


def create_tenant(body):
    _check_admin_permission()

    tenant_id = body.get('id', str(uuid.uuid4()))
    name = body.get('name')
    slug = body.get('slug')
    status_str = body.get('status', 'ACTIVE')

    if not name:
         raise ApiError(error_code="missing_name", message="Name is required", status_code=400)
    if not slug:
         raise ApiError(error_code="missing_slug", message="Slug is required", status_code=400)
    
    existing_tenant = M8flowTenantModel.query.filter_by(slug=slug).first()
    if existing_tenant:
        raise ApiError(
            error_code="tenant_slug_exists", 
            message=f"Tenant with slug '{slug}' already exists.", 
            status_code=409
        )

    # helper for metadata usually managed by mixins or explicitly
    current_user_id = g.user.username
    created_by = current_user_id
    modified_by = current_user_id
    
    tenant = M8flowTenantModel(
        id=tenant_id,
        name=name,
        slug=slug,
        status=TenantStatus(status_str),
        created_by=created_by,
        modified_by=modified_by
    )
    
    try:
        db.session.add(tenant)
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        # This handles race conditions where the check passed but insert failed
        raise ApiError(
            error_code="database_integrity_error", 
            message=f"Could not create tenant due to a database integrity error: {str(e)}", 
            status_code=409
        )
    except Exception as e:
        db.session.rollback()
        raise ApiError(
            error_code="database_error",
            message=str(e),
            status_code=500
        )
    
    return make_response(jsonify(tenant), 201)


def get_tenant_by_id(tenant_id):
    """Fetch tenant by ID."""
    _check_admin_permission()
    _check_not_default_tenant(tenant_id, "tenant")
    
    tenant = M8flowTenantModel.query.filter_by(id=tenant_id).first()
    
    if not tenant:
        raise ApiError(
            error_code="tenant_not_found",
            message=f"Tenant with ID '{tenant_id}' not found.",
            status_code=404
        )
    
    return make_response(jsonify(tenant), 200)


def get_tenant_by_slug(slug):
    """Fetch tenant by slug."""
    _check_admin_permission()
    _check_not_default_tenant(slug, "tenant")
    
    tenant = M8flowTenantModel.query.filter_by(slug=slug).first()
    
    if not tenant:
        raise ApiError(
            error_code="tenant_not_found",
            message=f"Tenant with slug '{slug}' not found.",
            status_code=404
        )
    
    return make_response(jsonify(tenant), 200)


def get_all_tenants():
    """Fetch all tenants, excluding the default tenant."""
    _check_admin_permission()
    
    try:
        # Filter out default tenant (by both id and slug)
        tenants = M8flowTenantModel.query.filter(
            M8flowTenantModel.id != "default",
            M8flowTenantModel.slug != "default"
        ).all()
        return make_response(jsonify(tenants), 200)
    except Exception as e:
        raise ApiError(
            error_code="database_error",
            message=f"Error fetching tenants: {str(e)}",
            status_code=500
        )

def delete_tenant(tenant_id):
    """Soft delete a tenant by setting status to DELETED."""
    _check_admin_permission()
    _check_not_default_tenant(tenant_id, "tenant")
    
    tenant = M8flowTenantModel.query.filter_by(id=tenant_id).first()
    
    if not tenant:
        raise ApiError(
            error_code="tenant_not_found",
            message=f"Tenant with ID '{tenant_id}' not found.",
            status_code=404
        )
    
    # Check if already deleted
    if tenant.status == TenantStatus.DELETED:
        raise ApiError(
            error_code="tenant_already_deleted",
            message=f"Tenant with ID '{tenant_id}' is already deleted.",
            status_code=400
        )
    
    try:
        # Soft delete - update status to DELETED
        tenant.status = TenantStatus.DELETED
        tenant.modified_by = g.user.username
        
        db.session.commit()
        
        return make_response(jsonify({
            "message": f"Tenant '{tenant.name}' has been successfully deleted.",
            "tenant": tenant
        }), 200)
    except Exception as e:
        db.session.rollback()
        raise ApiError(
            error_code="database_error",
            message=f"Error deleting tenant: {str(e)}",
            status_code=500
        )

def update_tenant(tenant_id, body):
    """Update tenant name and status. Slug cannot be updated."""
    _check_admin_permission()
    _check_not_default_tenant(tenant_id, "tenant")
    
    tenant = M8flowTenantModel.query.filter_by(id=tenant_id).first()
    
    if not tenant:
        raise ApiError(
            error_code="tenant_not_found",
            message=f"Tenant with ID '{tenant_id}' not found.",
            status_code=404
        )
    
    # Prevent updating DELETED tenants
    if tenant.status == TenantStatus.DELETED:
        raise ApiError(
            error_code="tenant_deleted",
            message=f"Cannot update tenant with ID '{tenant_id}' because it is deleted.",
            status_code=400
        )
    
    # Check if slug update is attempted (not allowed)
    if 'slug' in body and body['slug'] != tenant.slug:
        raise ApiError(
            error_code="slug_update_forbidden",
            message="Slug cannot be updated. It is immutable after creation.",
            status_code=400
        )
    
    # Extract updatable fields
    name = body.get('name')
    status_str = body.get('status')
    
    # Validate at least one field is being updated
    if not name and not status_str:
        raise ApiError(
            error_code="no_fields_to_update",
            message="At least one field (name or status) must be provided for update.",
            status_code=400
        )
    
    try:
        # Update name if provided
        if name:
            tenant.name = name
        
        # Update status if provided
        if status_str:
            try:
                tenant.status = TenantStatus(status_str)
            except ValueError:
                raise ApiError(
                    error_code="invalid_status",
                    message=f"Invalid status value: '{status_str}'. Must be one of: ACTIVE, INACTIVE, DELETED.",
                    status_code=400
                )
        
        # Update modified_by
        tenant.modified_by = g.user.username
        
        db.session.commit()
        
        return make_response(jsonify({
            "message": f"Tenant '{tenant.name}' has been successfully updated.",
            "tenant": tenant
        }), 200)
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

