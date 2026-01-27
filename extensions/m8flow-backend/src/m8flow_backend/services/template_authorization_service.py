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
    def can_view(cls, template: TemplateModel, user: UserModel | None = None) -> bool:
        # PUBLIC: anyone with auth context
        if template.is_public():
            return True

        # TENANT: must match tenant
        if template.is_tenant_visible():
            return cls._tenant_id() is not None and cls._tenant_id() == template.m8f_tenant_id

        # PRIVATE: must be creator and same tenant
        if template.is_private():
            return (
                user is not None
                and template.created_by == user.username
                and cls._tenant_id() is not None
                and cls._tenant_id() == template.m8f_tenant_id
            )
        return False

    @classmethod
    def can_edit(cls, template: TemplateModel, user: UserModel | None = None) -> bool:
        if user is None:
            return False

        # Owner can edit if not published
        if template.created_by == user.username and not template.is_published:
            return True

        # Admin/editor role check (reuse authorization service with a coarse permission)
        try:
            if AuthorizationService.user_has_permission(user, "admin", "/templates"):
                return True
            if AuthorizationService.user_has_permission(user, "editor", "/templates"):
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

        # PUBLIC or same tenant; private requires owner check in app layer
        return query.filter(
            or_(
                TemplateModel.visibility == TemplateVisibility.public.value,
                and_(
                    TemplateModel.visibility == TemplateVisibility.tenant.value,
                    TemplateModel.m8f_tenant_id == tenant_id
                ),
                and_(
                    TemplateModel.visibility == TemplateVisibility.private.value,
                    TemplateModel.m8f_tenant_id == tenant_id
                )
            )
        )
