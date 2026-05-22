from __future__ import annotations

from flask import g
from sqlalchemy import or_, and_

from spiffworkflow_backend.services.authorization_service import AuthorizationService
from spiffworkflow_backend.models.user import UserModel

from m8flow_backend.models.template import TemplateModel, TemplateVisibility


class TemplateAuthorizationService:
    """Visibility and edit rules for templates."""

    @staticmethod
    def _tenant_id() -> str | None:
        return getattr(g, "m8flow_tenant_id", None)

    @classmethod
    def has_admin_permission(cls, user: UserModel | None, permission: str) -> bool:
        """Check if user has admin-level permission on templates via RBAC.

        Delegates to AuthorizationService (backing /v1.0/permissions-check)
        instead of inspecting group membership directly.
        """
        if user is None:
            return False
        try:
            return AuthorizationService.user_has_permission(
                user, permission, "/m8flow/admin/templates"
            )
        except Exception:
            return False

    @classmethod
    def can_view(cls, template: TemplateModel, user: UserModel | None = None) -> bool:
        tenant_id = cls._tenant_id()

        # Admin can view any template in their tenant.
        if (
            user is not None
            and cls.has_admin_permission(user, "read")
            and tenant_id is not None
            and tenant_id == template.m8f_tenant_id
        ):
            return True

        # PUBLIC: anyone with auth context
        if template.is_public():
            return True

        # TENANT: must match tenant
        if template.is_tenant_visible():
            return tenant_id is not None and tenant_id == template.m8f_tenant_id

        # PRIVATE: must be creator and same tenant
        if template.is_private():
            return (
                user is not None
                and template.created_by == user.username
                and tenant_id is not None
                and tenant_id == template.m8f_tenant_id
            )
        return False

    @classmethod
    def can_edit(cls, template: TemplateModel, user: UserModel | None = None) -> bool:
        if user is None:
            return False

        # Owner can edit: in-place if unpublished, or create new version if published
        if template.created_by == user.username:
            return True

        # Permission check (Spiff permissions are CRUD: create/read/update/delete).
        try:
            if AuthorizationService.user_has_permission(user, "update",  "/m8flow/templates"):
                return True
        except Exception:
            # Fallback to owner-only if permission system is not configured for templates
            return False

        return False

    @classmethod
    def filter_query_by_visibility(cls, query, user: UserModel | None = None):
        """Apply visibility filters for the current tenant/user."""
        tenant_id = cls._tenant_id()
        if tenant_id is None:
            # No tenant context; default deny non-public
            return query.filter(TemplateModel.visibility == TemplateVisibility.public.value)

        # PUBLIC or same-tenant TENANT; PRIVATE only for owner
        conditions = [
            TemplateModel.visibility == TemplateVisibility.public.value,
            and_(
                TemplateModel.visibility == TemplateVisibility.tenant.value,
                TemplateModel.m8f_tenant_id == tenant_id
            ),
        ]
        if user is not None:
            if cls.has_admin_permission(user, "read"):
                conditions.append(
                    and_(
                        TemplateModel.visibility == TemplateVisibility.private.value,
                        TemplateModel.m8f_tenant_id == tenant_id,
                    )
                )
            else:
                conditions.append(
                    and_(
                        TemplateModel.visibility == TemplateVisibility.private.value,
                        TemplateModel.m8f_tenant_id == tenant_id,
                        TemplateModel.created_by == user.username
                    )
                )
        return query.filter(or_(*conditions))
