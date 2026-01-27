from __future__ import annotations

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.tenancy import (
    DEFAULT_TENANT_ID,
    allow_missing_tenant_context,
    get_context_tenant_id,
    get_tenant_id,
    is_public_request,
)


def require_valid_tenant() -> str:
    """
    Ensure the current tenant exists in DB.
    Call this only in places where Flask app context + db are available
    (i.e., inside request handlers/services, NOT before_request in Connexion 3).
    """
    if is_public_request():
        tenant_id = get_context_tenant_id()
        if not tenant_id:
            if allow_missing_tenant_context():
                tenant_id = DEFAULT_TENANT_ID
            else:
                raise RuntimeError("Missing tenant id in request context.")
    else:
        tenant_id = get_tenant_id()

    if db.session.get(M8flowTenantModel, tenant_id) is None:
        raise ApiError(
            error_code="invalid_tenant",
            message=f"Tenant '{tenant_id}' does not exist.",
            status_code=400,
        )

    return tenant_id
