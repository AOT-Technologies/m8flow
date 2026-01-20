from flask import jsonify, make_response, g, current_app
from sqlalchemy.exc import IntegrityError
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.exceptions.api_error import ApiError
import uuid

def create_tenant(body):
    if not hasattr(g, "user") or not g.user:
         raise ApiError(error_code="not_authenticated", message="User not authenticated", status_code=401)

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

