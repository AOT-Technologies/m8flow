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
        tenant_id = cls._tenant_id()

        # Tenant-admin can view any template in their tenant.
        if (
            user is not None
            and cls.is_tenant_admin(user)
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
        # TODO(RBAC): once m8flow has role-based permissions (e.g. admin/editor), map roles -> CRUD
        # for templates and/or add a dedicated role-aware check here.
        try:
            if AuthorizationService.user_has_permission(user, "update",  "/templates"):
                return True
        except Exception:
            # Fallback to owner-only if permission system is not configured for templates
            return False

        return False

    @staticmethod
    def _user_group_identifiers(user: UserModel | None = None) -> set[str]:
        if user is None or not hasattr(user, "groups"):
            return set()
        identifiers: set[str] = set()
        for group in getattr(user, "groups", []) or []:
            identifier = getattr(group, "identifier", None) or getattr(group, "name", None)
            if isinstance(identifier, str) and identifier:
                identifiers.add(identifier)
        return identifiers

    @classmethod
    def is_tenant_admin(cls, user: UserModel | None = None) -> bool:
        """Return True when user belongs to tenant-admin group (plain or tenant-qualified)."""
        for identifier in cls._user_group_identifiers(user):
            if identifier == "tenant-admin" or identifier.endswith(":tenant-admin"):
                return True
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
            if cls.is_tenant_admin(user):
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
