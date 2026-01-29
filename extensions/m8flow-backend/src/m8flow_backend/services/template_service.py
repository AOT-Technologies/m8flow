from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import g
from sqlalchemy import or_

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.user import UserModel

from m8flow_backend.models.template import TemplateModel, TemplateVisibility
from m8flow_backend.services.template_authorization_service import TemplateAuthorizationService
from m8flow_backend.services.template_storage_service import (
    FilesystemTemplateStorageService,
    NoopTemplateStorageService,
    TemplateStorageService,
)


class TemplateService:
    """Service for CRUD, versioning, and visibility enforcement for templates."""

    storage: TemplateStorageService = FilesystemTemplateStorageService()

    @staticmethod
    def _version_key(version: str) -> tuple:
        """Return a sortable key for V-prefixed versions like 'V1', 'V2'."""
        v = (version or "").strip()
        if v and v[0] in ("V", "v") and v[1:].isdigit():
            # Known V-style version: sort by numeric value, after any legacy/unknown formats.
            return (1, int(v[1:]))
        # Fallback for any unexpected/legacy formats (we no longer actively support them)
        return (0, v)

    @classmethod
    def _next_version(cls, template_key: str, tenant_id: str) -> str:
        """Get the next version for a template key within a specific tenant, using V-prefixed versions."""
        # Filter by both template_key AND tenant_id to scope versioning per tenant
        query = TemplateModel.query.filter_by(
            template_key=template_key,
            m8f_tenant_id=tenant_id
        )
        rows = query.all()
        
        if not rows:
            return "V1"
        
        # Find the latest version for this tenant
        latest = max(rows, key=lambda r: cls._version_key(r.version))
        latest_version = (latest.version or "").strip()

        if latest_version and latest_version[0] in ("V", "v") and latest_version[1:].isdigit():
            next_number = int(latest_version[1:]) + 1
            return f"V{next_number}"

        # If the latest version is in some unexpected/legacy format, start the V-series at V1
        return "V1"

    @classmethod
    def create_template(
        cls,
        bpmn_bytes: bytes | None,
        metadata: dict[str, Any] | None,
        user: UserModel | None = None,
        tenant_id: str | None = None,
    ) -> TemplateModel:
        """Create a template using BPMN bytes and metadata from headers."""
        if user is None:
            raise ApiError("unauthorized", "User must be authenticated to create templates", status_code=403)

        tenant = tenant_id or getattr(g, "m8flow_tenant_id", None)
        if tenant is None:
            raise ApiError("tenant_required", "Tenant context required", status_code=400)

        if metadata is None:
            raise ApiError("missing_fields", "metadata is required", status_code=400)

        template_key = metadata.get("template_key")
        name = metadata.get("name")
        provided_version = metadata.get("version")
        visibility = metadata.get("visibility", TemplateVisibility.private.value)
        tags = metadata.get("tags")
        category = metadata.get("category")
        description = metadata.get("description")
        status = metadata.get("status", "draft")
        is_published = bool(metadata.get("is_published", False))
        bpmn_object_key = None  # Will be generated from storage

        if not template_key or not name:
            raise ApiError("missing_fields", "template_key and name are required", status_code=400)

        version = provided_version or cls._next_version(template_key, tenant)

        # Store BPMN file (now required)
        if bpmn_bytes is not None:
            bpmn_object_key = cls.storage.store_bpmn(template_key, version, bpmn_bytes, tenant)
        else:
            raise ApiError("missing_fields", "bpmn_content is required", status_code=400)

        username = getattr(g, "user", None)
        username_str = username.username if username and hasattr(username, "username") else None
        if username_str is None:
            raise ApiError("unauthorized", "User username not found in request context", status_code=403)

        template = TemplateModel(
            template_key=template_key,
            version=version,
            name=name,
            description=description,
            tags=tags,
            category=category,
            m8f_tenant_id=tenant,
            visibility=visibility,
            bpmn_object_key=bpmn_object_key,
            is_published=is_published,
            status=status,
            created_by=username_str,
            modified_by=username_str,
        )
        db.session.add(template)
        TemplateModel.commit_with_rollback_on_exception()
        return template

    @classmethod
    def list_templates(
        cls,
        user: UserModel | None,
        tenant_id: str | None = None,
        latest_only: bool = True,
        category: str | None = None,
        tag: str | None = None,
        owner: str | None = None,
        visibility: str | None = None,
        search: str | None = None,
    ) -> list[TemplateModel]:
        query = TemplateModel.query
        query = TemplateAuthorizationService.filter_query_by_visibility(query, user=user)
        query = query.filter(TemplateModel.is_deleted.is_(False))
        
        # Filter by tenant if provided (ensure tenant isolation)
        tenant = tenant_id or getattr(g, "m8flow_tenant_id", None)
        if tenant:
            query = query.filter(TemplateModel.m8f_tenant_id == tenant)

        # Apply filters
        if category:
            query = query.filter(TemplateModel.category == category)
        
        if owner:
            query = query.filter(TemplateModel.created_by == owner)
        
        if visibility:
            query = query.filter(TemplateModel.visibility == visibility)
        
        if search:
            # Text search in name and description
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    TemplateModel.name.ilike(search_pattern),
                    TemplateModel.description.ilike(search_pattern)
                )
            )

        results: list[TemplateModel] = query.all()
        
        # Filter by tags if provided (after query execution for JSON array compatibility)
        if tag:
            tag_list = [t.strip() for t in tag.split(",") if t.strip()]
            if tag_list:
                filtered_results = []
                for row in results:
                    if row.tags and isinstance(row.tags, list):
                        # Check if any tag in tag_list matches any tag in row.tags
                        if any(t in row.tags for t in tag_list):
                            filtered_results.append(row)
                    elif row.tags and isinstance(row.tags, str):
                        # Handle case where tags might be stored as string
                        if any(t in str(row.tags) for t in tag_list):
                            filtered_results.append(row)
                results = filtered_results
        
        if not latest_only:
            return results

        # Scope latest versions by tenant + template_key combination
        latest_per_tenant_key: dict[tuple[str, str], TemplateModel] = {}
        for row in results:
            key = (row.m8f_tenant_id or "", row.template_key)
            current = latest_per_tenant_key.get(key)
            if current is None or cls._version_key(row.version) > cls._version_key(current.version):
                latest_per_tenant_key[key] = row
        return list(latest_per_tenant_key.values())

    @classmethod
    def get_template(
        cls,
        template_key: str,
        version: str | None = None,
        latest: bool = False,
        user: UserModel | None = None,
        suppress_visibility: bool = False,
        tenant_id: str | None = None,
    ) -> TemplateModel | None:
        """Get template by key, scoped to tenant."""
        query = TemplateModel.query.filter_by(template_key=template_key)
        
        # Filter by tenant to ensure tenant isolation
        tenant = tenant_id or getattr(g, "m8flow_tenant_id", None)
        if tenant:
            query = query.filter(TemplateModel.m8f_tenant_id == tenant)

        # Exclude soft-deleted templates by default
        query = query.filter(TemplateModel.is_deleted.is_(False))
        
        if not suppress_visibility:
            query = TemplateAuthorizationService.filter_query_by_visibility(query, user=user)

        if version:
            return query.filter_by(version=version).first()

        # latest - already filtered by tenant above
        rows = query.all()
        if not rows:
            return None
        return max(rows, key=lambda r: cls._version_key(r.version))

    @classmethod
    def get_template_by_id(
        cls,
        template_id: int,
        user: UserModel | None = None,
    ) -> TemplateModel | None:
        """Get template by database ID with visibility checks, excluding soft-deleted templates."""
        template = TemplateModel.query.filter_by(id=template_id).filter(TemplateModel.is_deleted.is_(False)).first()
        if template is None:
            return None
        
        # Check visibility
        if not TemplateAuthorizationService.can_view(template, user):
            return None
        
        return template

    @classmethod
    def update_template(
        cls,
        template_key: str,
        version: str,
        updates: dict[str, Any],
        user: UserModel | None,
    ) -> TemplateModel:
        template = cls.get_template(template_key, version, user=user)
        if template is None:
            raise ApiError("not_found", "Template version not found", status_code=404)
        if template.is_published:
            raise ApiError("immutable", "Published template versions cannot be updated", status_code=400)
        if not TemplateAuthorizationService.can_edit(template, user):
            raise ApiError("forbidden", "You cannot edit this template", status_code=403)

        for field in ["name", "description", "tags", "category", "visibility", "bpmn_object_key", "status"]:
            if field in updates:
                setattr(template, field, updates[field])
        
        username = getattr(g, "user", None)
        template.modified_by = username.username if username and hasattr(username, "username") else template.modified_by
        TemplateModel.commit_with_rollback_on_exception()
        return template

    @classmethod
    def update_template_by_id(
        cls,
        template_id: int,
        updates: dict[str, Any],
        bpmn_bytes: bytes | None = None,
        user: UserModel | None = None,
    ) -> TemplateModel:
        """Update template by ID - updates in place if not published, creates new version if published."""
        # Get the existing template
        existing_template = cls.get_template_by_id(template_id, user=user)
        if existing_template is None:
            raise ApiError("not_found", "Template not found", status_code=404)
        
        if not TemplateAuthorizationService.can_edit(existing_template, user):
            raise ApiError("forbidden", "You cannot edit this template", status_code=403)
        
        # Get current user info
        username = getattr(g, "user", None)
        username_str = username.username if username and hasattr(username, "username") else None
        if username_str is None:
            raise ApiError("unauthorized", "User username not found in request context", status_code=403)
        
        tenant = existing_template.m8f_tenant_id
        
        # Handle BPMN content update if provided
        if bpmn_bytes is not None:
            # Store new BPMN file
            if not existing_template.is_published:
                # Update in place - overwrite existing file
                new_bpmn_object_key = cls.storage.store_bpmn(
                    existing_template.template_key, existing_template.version, bpmn_bytes, tenant
                )
            else:
                # Create new version - will create new file with new version
                next_version = cls._next_version(existing_template.template_key, tenant)
                new_bpmn_object_key = cls.storage.store_bpmn(
                    existing_template.template_key, next_version, bpmn_bytes, tenant
                )
        else:
            new_bpmn_object_key = None
        
        allowed_fields = ["name", "description", "tags", "category", "visibility", "bpmn_object_key", "status"]
        
        # If template is not published, update in place
        if not existing_template.is_published:
            # Update the existing template record in place
            for field in allowed_fields:
                if field in updates:
                    setattr(existing_template, field, updates[field])
            
            # Update BPMN object key if new BPMN was provided
            if new_bpmn_object_key:
                existing_template.bpmn_object_key = new_bpmn_object_key
            
            existing_template.modified_by = username_str
            existing_template.updated_at = datetime.now(timezone.utc)
            TemplateModel.commit_with_rollback_on_exception()
            return existing_template
        
        # If template is published, create a new version
        # Calculate next version
        next_version = cls._next_version(existing_template.template_key, tenant)
        
        # Create new template version with copied fields
        new_template = TemplateModel(
            template_key=existing_template.template_key,
            version=next_version,
            name=existing_template.name,
            description=existing_template.description,
            tags=existing_template.tags,
            category=existing_template.category,
            m8f_tenant_id=existing_template.m8f_tenant_id,
            visibility=existing_template.visibility,
            bpmn_object_key=new_bpmn_object_key or existing_template.bpmn_object_key,
            is_published=False,  # New versions start as unpublished
            status=existing_template.status,
            created_by=username_str,
            modified_by=username_str,
        )
        
        # Apply updates
        for field in allowed_fields:
            if field in updates:
                setattr(new_template, field, updates[field])
        
        db.session.add(new_template)
        TemplateModel.commit_with_rollback_on_exception()
        return new_template

    @classmethod
    def delete_template_by_id(
        cls,
        template_id: int,
        user: UserModel | None,
    ) -> None:
        """Soft delete template by ID (mark as deleted without removing row)."""
        template = cls.get_template_by_id(template_id, user=user)
        if template is None:
            raise ApiError("not_found", "Template not found", status_code=404)
        
        if template.is_published:
            raise ApiError("immutable", "Published template versions cannot be deleted", status_code=400)
        
        if not TemplateAuthorizationService.can_edit(template, user):
            raise ApiError("forbidden", "You cannot delete this template", status_code=403)

        # Mark as soft-deleted
        template.is_deleted = True

        TemplateModel.commit_with_rollback_on_exception()
