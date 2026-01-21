from flask import jsonify, make_response, g
from functools import wraps
from sqlalchemy.exc import IntegrityError
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.authorization_service import AuthorizationService
import uuid

def _success_response(data, status_code=200):
    """Helper to create standardized success response."""
    return make_response(jsonify({
        "success": True,
        "statusCode": status_code,
        "data": data
    }), status_code)

def _get_tenant_or_raise(tenant_id):
    """Fetch tenant by ID or raise appropriate error."""
    _check_not_default_tenant(tenant_id, "tenant")
    
    tenant = M8flowTenantModel.query.filter_by(id=tenant_id).first()
    
    if not tenant:
        raise ApiError(
            error_code="tenant_not_found",
            message=f"Tenant with ID '{tenant_id}' not found.",
            status_code=404
        )
    return tenant

def handle_api_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ApiError as e:
            # ApiError attributes are snake_case (error_code, status_code)
            # We map them to camelCase for the JSON response
            status_code = getattr(e, 'status_code', 400)
            error_code = getattr(e, 'error_code', 'unknown_error')
            
            return make_response(jsonify({
                "success": False,
                "statusCode": status_code,
                "data": {
                    "errorCode": error_code,
                    "message": e.message
                }
            }), status_code)
        except Exception as e:
            # Catch-all for unexpected errors
            return make_response(jsonify({
                "success": False,
                "statusCode": 500,
                "data": {
                    "errorCode": "internal_server_error",
                    "message": str(e)
                }
            }), 500)
    return decorated_function

def _check_admin_permission():
    """Check if user has admin permission to manage tenants."""
    if not hasattr(g, "user") or not g.user:
        raise ApiError(error_code="not_authenticated", message="User not authenticated", status_code=401)
    
    # Check if user has permission to manage tenants (admin/system role)
    has_permission = AuthorizationService.user_has_permission(
        user=g.user,
        permission="create",
        target_uri="/admin/tenants"  # Must be snake_case target_uri
    )
    
    if not has_permission:
        raise ApiError(
            error_code="insufficient_permissions",
            message="User does not have sufficient permissions to manage tenants. Admin or system role required.",
            status_code=403
        )

def _check_not_default_tenant(identifier: str, identifier_type: str = "tenant"):
    """Check that the given identifier is not 'default' to prevent operations on default tenant."""
    if identifier and identifier.lower() == "default":
        raise ApiError(
            error_code="forbidden_tenant",
            message=f"Cannot perform operations on default {identifier_type}.",
            status_code=403
        )

@handle_api_errors
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
    
    # Check if ID already exists if explicitly provided
    if 'id' in body:
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
        created_by=g.user.username,
        modified_by=g.user.username
    )
    
    try:
        db.session.add(tenant)
        db.session.commit()
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
    
    return _success_response(tenant, 201)


@handle_api_errors
def get_tenant_by_id(tenant_id):
    """Fetch tenant by ID."""
    _check_admin_permission()
    tenant = _get_tenant_or_raise(tenant_id)
    return _success_response(tenant, 200)


@handle_api_errors
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
    
    return _success_response(tenant, 200)


@handle_api_errors
def get_all_tenants():
    """Fetch all tenants, excluding the default tenant."""
    _check_admin_permission()
    
    try:
        tenants = M8flowTenantModel.query.filter(
            M8flowTenantModel.id != "default",
            M8flowTenantModel.slug != "default"
        ).all()
        return _success_response(tenants, 200)
    except Exception as e:
        raise ApiError(
            error_code="database_error",
            message=f"Error fetching tenants: {str(e)}",
            status_code=500
        )

@handle_api_errors
def delete_tenant(tenant_id):
    """Soft delete a tenant by setting status to DELETED."""
    _check_admin_permission()
    tenant = _get_tenant_or_raise(tenant_id)
    
    if tenant.status == TenantStatus.DELETED:
        raise ApiError(
            error_code="tenant_already_deleted",
            message=f"Tenant with ID '{tenant_id}' is already deleted.",
            status_code=400
        )
    
    try:
        tenant.status = TenantStatus.DELETED
        tenant.modified_by = g.user.username
        
        db.session.commit()
        
        return _success_response({
            "message": f"Tenant '{tenant.name}' has been successfully deleted.",
            "tenant": tenant
        }, 200)
    except Exception as e:
        db.session.rollback()
        raise ApiError(
            error_code="database_error",
            message=f"Error deleting tenant: {str(e)}",
            status_code=500
        )

@handle_api_errors
def update_tenant(tenant_id, body):
    """Update tenant name and status. Slug cannot be updated."""
    _check_admin_permission()
    tenant = _get_tenant_or_raise(tenant_id)
    
    if tenant.status == TenantStatus.DELETED:
        raise ApiError(
            error_code="tenant_deleted",
            message=f"Cannot update tenant with ID '{tenant_id}' because it is deleted.",
            status_code=400
        )
    
    if 'slug' in body and body['slug'] != tenant.slug:
        raise ApiError(
            error_code="slug_update_forbidden",
            message="Slug cannot be updated. It is immutable after creation.",
            status_code=400
        )
    
    name = body.get('name')
    status_str = body.get('status')
    
    if not name and not status_str:
        raise ApiError(
            error_code="no_fields_to_update",
            message="At least one field (name or status) must be provided for update.",
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
        
        tenant.modified_by = g.user.username
        db.session.commit()
        
        return _success_response({
            "message": f"Tenant '{tenant.name}' has been successfully updated.",
            "tenant": tenant
        }, 200)
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
