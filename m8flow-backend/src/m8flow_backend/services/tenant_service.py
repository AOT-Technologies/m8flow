from __future__ import annotations

import re

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from m8flow_backend.db import db
from m8flow_backend.errors import ApiError

MAX_TENANT_NAME_LENGTH = 50
# Letters/digits (Unicode), then letters, digits, space, - _ . &
_TENANT_NAME_RE = re.compile(r"[^\W_][\w .&-]*")
INVALID_TENANT_NAME_MESSAGE = (
    "Tenant name can only contain letters, numbers, spaces, and - _ . & "
    "and must start with a letter or number."
)


class TenantService:
    @staticmethod
    def validate_name(name: str) -> str | None:
        """Return an error message if the (already trimmed) tenant display name is invalid."""
        if not name:
            return "Tenant name cannot be empty."
        if len(name) > MAX_TENANT_NAME_LENGTH:
            return f"Tenant name must be {MAX_TENANT_NAME_LENGTH} characters or fewer."
        if not _TENANT_NAME_RE.fullmatch(name):
            return INVALID_TENANT_NAME_MESSAGE
        return None

    @staticmethod
    def get_tenant_by_id(tenant_id: str):
        tenant = db.session.query(M8flowTenantModel).filter_by(id=tenant_id).first()
        
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
            db.session.query(M8flowTenantModel).filter(
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
    def name_exists(name: str, exclude_tenant_id: str | None = None) -> bool:
        """Return True if another tenant already uses the given display name (case-insensitive)."""
        if not name or not name.strip():
            return False
        normalized = name.strip().lower()
        query = db.session.query(M8flowTenantModel).filter(
            db.func.lower(M8flowTenantModel.name) == normalized
        )
        if exclude_tenant_id:
            query = query.filter(M8flowTenantModel.id != exclude_tenant_id)
        return db.session.query(query.exists()).scalar()

    @staticmethod
    def get_tenant_by_slug(slug: str):
        tenant = db.session.query(M8flowTenantModel).filter_by(slug=slug).first()
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
            return db.session.query(M8flowTenantModel).all()
        except Exception as e:
            raise ApiError(
                error_code="database_error",
                message=f"Error fetching tenants: {str(e)}",
                status_code=500
            )
