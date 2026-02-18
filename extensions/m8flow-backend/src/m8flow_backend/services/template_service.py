from __future__ import annotations

import io
import logging
import os
import random
import re
import string
import zipfile
from datetime import datetime, timezone
from typing import Any

from flask import g
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.process_model import ProcessModelInfo
from spiffworkflow_backend.models.user import UserModel
from spiffworkflow_backend.routes.process_api_blueprint import _commit_and_push_to_git
from spiffworkflow_backend.services.process_model_service import ProcessModelService
from spiffworkflow_backend.services.spec_file_service import SpecFileService

from m8flow_backend.models.process_model_template import ProcessModelTemplateModel
from m8flow_backend.models.template import TemplateModel, TemplateVisibility
from m8flow_backend.services.template_authorization_service import TemplateAuthorizationService
from m8flow_backend.services.template_storage_service import (
    FilesystemTemplateStorageService,
    NoopTemplateStorageService,
    TemplateStorageService,
    file_type_from_filename,
)

logger = logging.getLogger(__name__)

# Zip import safety limits
MAX_ZIP_SIZE = 50 * 1024 * 1024        # 50 MB compressed
MAX_EXTRACTED_SIZE = 200 * 1024 * 1024  # 200 MB total uncompressed
MAX_ZIP_ENTRIES = 100

UNIQUE_TEMPLATE_CONSTRAINT = "uq_template_key_version_tenant"  # keep in sync with TemplateModel __table_args__

TENANT_REQUIRED_MESSAGE = "Tenant context required"


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
        """Create a template with a single BPMN file (backward-compat)."""
        if bpmn_bytes is None:
            raise ApiError("missing_fields", "bpmn_content is required", status_code=400)
        return cls.create_template_with_files(
            metadata=metadata,
            files=[("diagram.bpmn", bpmn_bytes)],
            user=user,
            tenant_id=tenant_id,
        )

    @classmethod
    def create_template_with_files(
        cls,
        metadata: dict[str, Any],
        files: list[tuple[str, bytes]],
        user: UserModel | None = None,
        tenant_id: str | None = None,
    ) -> TemplateModel:
        """Create a template with multiple files. At least one must be BPMN."""
        if user is None:
            raise ApiError("unauthorized", "User must be authenticated to create templates", status_code=403)

        tenant = tenant_id or getattr(g, "m8flow_tenant_id", None)
        if tenant is None:
            raise ApiError("tenant_required", TENANT_REQUIRED_MESSAGE, status_code=400)

        if not metadata:
            raise ApiError("missing_fields", "metadata is required", status_code=400)

        template_key = metadata.get("template_key")
        name = metadata.get("name")
        if not template_key or not name:
            raise ApiError("missing_fields", "template_key and name are required", status_code=400)

        version = metadata.get("version") or cls._next_version(template_key, tenant)
        visibility = metadata.get("visibility", TemplateVisibility.private.value)
        tags = metadata.get("tags")
        category = metadata.get("category")
        description = metadata.get("description")
        status = metadata.get("status", "draft")
        is_published = bool(metadata.get("is_published", False))

        has_bpmn = any(
            file_type_from_filename(fname) == "bpmn" for fname, _ in files
        )
        if not has_bpmn:
            raise ApiError("missing_fields", "At least one BPMN file is required", status_code=400)

        file_entries: list[dict] = []
        for file_name, content in files:
            ft = file_type_from_filename(file_name)
            cls.storage.store_file(tenant, template_key, version, file_name, ft, content)
            file_entries.append({"file_type": ft, "file_name": file_name})

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
            files=file_entries,
            is_published=is_published,
            status=status,
            created_by=username_str,
            modified_by=username_str,
        )
        try:
            db.session.add(template)
            TemplateModel.commit_with_rollback_on_exception()
            return template
        except IntegrityError as exc:
            db.session.rollback()
            # Generic detection based on constraint name rather than DB-specific codes.
            # For other integrity errors (NOT NULL, FK, etc.), let them surface normally.
            message = str(getattr(exc, "orig", exc))
            if UNIQUE_TEMPLATE_CONSTRAINT in message:
                raise ApiError(
                    error_code="template_conflict",
                    message="A template with this key and version already exists for this tenant.",
                    status_code=409,
                ) from exc
            raise

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
        template_key: str | None = None,
        published_only: bool = False,
        sort_by: str | None = None,
        order: str = "desc",
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[list[TemplateModel], dict]:
        query = TemplateModel.query
        query = TemplateAuthorizationService.filter_query_by_visibility(query, user=user)
        query = query.filter(TemplateModel.is_deleted.is_(False))
        
        # Filter by tenant: show current tenant's templates + PUBLIC templates from any tenant
        tenant = tenant_id or getattr(g, "m8flow_tenant_id", None)
        if tenant:
            query = query.filter(
                or_(
                    TemplateModel.m8f_tenant_id == tenant,
                    TemplateModel.visibility == TemplateVisibility.public.value,
                )
            )

        # Apply filters
        if category:
            query = query.filter(TemplateModel.category == category)
        
        if owner:
            query = query.filter(TemplateModel.created_by == owner)
        
        if visibility:
            query = query.filter(TemplateModel.visibility == visibility)
        
        if template_key:
            query = query.filter(TemplateModel.template_key == template_key)

        if published_only:
            query = query.filter(TemplateModel.is_published.is_(True))

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
        
        if latest_only:
            # Scope latest versions by tenant + template_key combination
            latest_per_tenant_key: dict[tuple[str, str], TemplateModel] = {}
            for row in results:
                key = (row.m8f_tenant_id or "", row.template_key)
                current = latest_per_tenant_key.get(key)
                if current is None or cls._version_key(row.version) > cls._version_key(current.version):
                    latest_per_tenant_key[key] = row
            results = list(latest_per_tenant_key.values())

        # Sort: created (by created_at_in_seconds) or name (case-insensitive)
        if sort_by in ("created", "name"):
            reverse = order.lower() == "desc"
            if sort_by == "created":
                results = sorted(results, key=lambda r: getattr(r, "created_at_in_seconds", 0) or 0, reverse=reverse)
            else:
                results = sorted(results, key=lambda r: (r.name or "").lower(), reverse=reverse)

        # Paginate the final filtered results
        total = len(results)
        per_page = max(1, min(per_page, 100))
        pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, pages))
        start = (page - 1) * per_page
        items = results[start : start + per_page]
        pagination = {"count": len(items), "total": total, "pages": pages}
        return items, pagination

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

        for field in ["name", "description", "tags", "category", "visibility", "status", "files"]:
            if field in updates:
                setattr(template, field, updates[field])

        username = getattr(g, "user", None)
        template.modified_by = username.username if username and hasattr(username, "username") else template.modified_by
        TemplateModel.commit_with_rollback_on_exception()
        return template

    @classmethod
    def _get_or_create_draft_version(
        cls,
        published_template: TemplateModel,
        user: UserModel | None = None,
    ) -> TemplateModel:
        """Find the latest draft version for this template key, or create one from the published template.

        This ensures we don't create multiple draft versions - edits accumulate on one draft.
        """
        tenant = published_template.m8f_tenant_id
        key = published_template.template_key

        # Look for existing draft version (unpublished, not deleted)
        existing_draft = (
            TemplateModel.query
            .filter_by(
                template_key=key,
                m8f_tenant_id=tenant,
                is_published=False,
                is_deleted=False,
            )
            .order_by(TemplateModel.id.desc())  # Get the latest draft
            .first()
        )

        if existing_draft:
            return existing_draft

        # No draft exists - create new version from published template
        username = getattr(g, "user", None)
        username_str = username.username if username and hasattr(username, "username") else "unknown"

        next_version = cls._next_version(key, tenant)

        # Copy all files to new version
        new_files: list[dict] = []
        for entry in (published_template.files or []):
            fname = entry.get("file_name")
            if not fname:
                continue
            try:
                content = cls.storage.get_file(tenant, key, published_template.version, fname)
                ft = entry.get("file_type", file_type_from_filename(fname))
                cls.storage.store_file(tenant, key, next_version, fname, ft, content)
                new_files.append({"file_type": ft, "file_name": fname})
            except ApiError as e:
                logger.warning("Failed to copy file %s for new version %s: %s", fname, next_version, e)

        if not new_files:
            raise ApiError(
                "storage_error",
                "Failed to copy any files for the new template version",
                status_code=500,
            )

        new_template = TemplateModel(
            template_key=key,
            version=next_version,
            name=published_template.name,
            description=published_template.description,
            tags=published_template.tags,
            category=published_template.category,
            m8f_tenant_id=tenant,
            visibility=published_template.visibility,
            files=new_files,
            is_published=False,
            status="draft",
            created_by=username_str,
            modified_by=username_str,
        )

        db.session.add(new_template)
        TemplateModel.commit_with_rollback_on_exception()

        return new_template

    @classmethod
    def update_template_by_id(
        cls,
        template_id: int,
        updates: dict[str, Any],
        bpmn_bytes: bytes | None = None,
        bpmn_file_name: str | None = None,
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
        key = existing_template.template_key
        version = existing_template.version
        files_list = list(existing_template.files or [])

        # Handle BPMN content update if provided (replace specific file by name, or first bpmn)
        if bpmn_bytes is not None:
            bpmn_name = bpmn_file_name or "diagram.bpmn"
            ft = "bpmn"
            if not existing_template.is_published:
                if bpmn_file_name:
                    # Update only the file with this name if it exists
                    found = any(
                        e.get("file_name") == bpmn_file_name and e.get("file_type") == "bpmn"
                        for e in files_list
                    )
                    if found:
                        cls.storage.store_file(tenant, key, version, bpmn_file_name, ft, bpmn_bytes)
                    else:
                        cls.storage.store_file(tenant, key, version, bpmn_file_name, ft, bpmn_bytes)
                        files_list.append({"file_type": ft, "file_name": bpmn_file_name})
                else:
                    # Replace first bpmn or add (backward compatibility)
                    for entry in files_list:
                        if entry.get("file_type") == "bpmn":
                            bpmn_name = entry.get("file_name", bpmn_name)
                            cls.storage.store_file(tenant, key, version, bpmn_name, ft, bpmn_bytes)
                            break
                    else:
                        cls.storage.store_file(tenant, key, version, bpmn_name, ft, bpmn_bytes)
                        files_list.append({"file_type": ft, "file_name": bpmn_name})
            else:
                # Published: will create new version in the loop below; bpmn_bytes applied there by file name
                pass

        allowed_fields = ["name", "description", "tags", "category", "visibility", "status"]

        if not existing_template.is_published:
            if updates.get("is_published") is True:
                existing_template.is_published = True
                existing_template.status = "published"
            for field in allowed_fields:
                if field in updates:
                    setattr(existing_template, field, updates[field])
            if files_list:
                existing_template.files = files_list
            existing_template.modified_by = username_str
            TemplateModel.commit_with_rollback_on_exception()
            return existing_template

        # Published: find or create draft version, then apply updates
        target_template = cls._get_or_create_draft_version(existing_template, user)

        # Apply BPMN content update if provided
        if bpmn_bytes is not None:
            bpmn_name = bpmn_file_name or "diagram.bpmn"
            ft = "bpmn"
            target_files = list(target_template.files or [])

            if bpmn_file_name:
                # Update specific file by name
                found = any(
                    e.get("file_name") == bpmn_file_name and e.get("file_type") == "bpmn"
                    for e in target_files
                )
                if found:
                    cls.storage.store_file(target_template.m8f_tenant_id, target_template.template_key,
                                          target_template.version, bpmn_file_name, ft, bpmn_bytes)
                else:
                    cls.storage.store_file(target_template.m8f_tenant_id, target_template.template_key,
                                          target_template.version, bpmn_file_name, ft, bpmn_bytes)
                    target_files.append({"file_type": ft, "file_name": bpmn_file_name})
                    target_template.files = target_files
            else:
                # Replace first bpmn or add (backward compatibility)
                replaced = False
                for entry in target_files:
                    if entry.get("file_type") == "bpmn":
                        bpmn_name = entry.get("file_name", bpmn_name)
                        cls.storage.store_file(target_template.m8f_tenant_id, target_template.template_key,
                                              target_template.version, bpmn_name, ft, bpmn_bytes)
                        replaced = True
                        break
                if not replaced:
                    cls.storage.store_file(target_template.m8f_tenant_id, target_template.template_key,
                                          target_template.version, bpmn_name, ft, bpmn_bytes)
                    target_files.append({"file_type": ft, "file_name": bpmn_name})
                    target_template.files = target_files

        # Apply metadata updates (but not is_published - draft stays draft)
        for field in allowed_fields:
            if field == "status":
                continue  # keep draft status
            if field in updates:
                setattr(target_template, field, updates[field])
        try:
            target_template.modified_by = username_str
            TemplateModel.commit_with_rollback_on_exception()
        except IntegrityError:
            db.session.rollback()
            raise ApiError(
                error_code="template_conflict",
                message="A template with this key and version already exists for this tenant.",
                status_code=409,
            )
        return target_template

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

    @classmethod
    def get_file_content(
        cls,
        template: TemplateModel,
        file_name: str,
    ) -> bytes:
        """Get content of one file by name. Raises ApiError if not found."""
        return cls.storage.get_file(
            template.m8f_tenant_id,
            template.template_key,
            template.version,
            file_name,
        )

    @classmethod
    def get_first_bpmn_content(cls, template: TemplateModel) -> bytes | None:
        """Return content of first BPMN file, or None if none."""
        for entry in template.files or []:
            if entry.get("file_type") == "bpmn":
                fname = entry.get("file_name")
                if fname:
                    try:
                        return cls.get_file_content(template, fname)
                    except ApiError:
                        continue
        return None

    @classmethod
    def update_file_content(
        cls,
        template: TemplateModel,
        file_name: str,
        content: bytes,
        user: UserModel | None = None,
    ) -> TemplateModel:
        """Update content of an existing file.

        If template is published, finds or creates a draft version and updates there.
        Returns the template that was actually updated (may be different from input if published).
        """
        # Find the file in the template
        found = None
        for e in template.files or []:
            if e.get("file_name") == file_name:
                found = e
                break
        if not found:
            raise ApiError("not_found", f"File not found: {file_name}", status_code=404)

        if not template.is_published:
            # Update in place
            ft = found.get("file_type") or file_type_from_filename(file_name)
            cls.storage.store_file(
                template.m8f_tenant_id,
                template.template_key,
                template.version,
                file_name,
                ft,
                content,
            )
            return template

        # Template is published - find or create draft version
        target_template = cls._get_or_create_draft_version(template, user)

        # Update the file in the target template
        ft = found.get("file_type") or file_type_from_filename(file_name)
        cls.storage.store_file(
            target_template.m8f_tenant_id,
            target_template.template_key,
            target_template.version,
            file_name,
            ft,
            content,
        )
        return target_template

    @classmethod
    def delete_file_from_template(
        cls,
        template: TemplateModel,
        file_name: str,
        user: UserModel | None = None,
    ) -> TemplateModel:
        """Remove a file from the template. Cannot delete last file or only BPMN.

        If template is published, finds or creates a draft version and deletes from there.
        Returns the template that was actually modified (may be different from input if published).
        """
        # Validate the file exists in the template
        files_list = list(template.files or [])
        if not files_list:
            raise ApiError("not_found", "Template has no files", status_code=404)

        file_exists = any(e.get("file_name") == file_name for e in files_list)
        if not file_exists:
            raise ApiError("not_found", f"File not found: {file_name}", status_code=404)

        # Check what would remain after deletion
        remaining = [e for e in files_list if e.get("file_name") != file_name]
        if len(remaining) == 0:
            raise ApiError(
                "forbidden",
                "Cannot delete the last file from a template",
                status_code=403,
            )
        has_bpmn_after = any(e.get("file_type") == "bpmn" for e in remaining)
        if not has_bpmn_after:
            raise ApiError(
                "forbidden",
                "Template must have at least one BPMN file",
                status_code=403,
            )

        # Determine target template (draft version if published)
        if template.is_published:
            target_template = cls._get_or_create_draft_version(template, user)
            # Recalculate remaining for the target template
            target_files = list(target_template.files or [])
            remaining = [e for e in target_files if e.get("file_name") != file_name]
        else:
            target_template = template

        # Update the template's file list
        target_template.files = remaining
        if user and hasattr(user, "username"):
            target_template.modified_by = user.username
        target_template.modified_at = datetime.now(timezone.utc)
        TemplateModel.commit_with_rollback_on_exception()

        # Delete the actual file from storage
        try:
            cls.storage.delete_file(
                target_template.m8f_tenant_id,
                target_template.template_key,
                target_template.version,
                file_name,
            )
        except Exception:
            pass

        return target_template

    @classmethod
    def export_template_zip(
        cls,
        template_id: int,
        user: UserModel | None = None,
    ) -> tuple[bytes, str]:
        """Return (zip bytes, suggested filename)."""
        template = cls.get_template_by_id(template_id, user=user)
        if template is None:
            raise ApiError("not_found", "Template not found", status_code=404)
        entries = template.files or []
        if not entries:
            raise ApiError("not_found", "Template has no files to export", status_code=404)
        zip_bytes = cls.storage.stream_zip(
            template.m8f_tenant_id,
            template.template_key,
            template.version,
            entries,
        )
        filename = f"template-{template.template_key}-{template.version}.zip"
        return zip_bytes, filename

    @classmethod
    def import_template_from_zip(
        cls,
        zip_bytes: bytes,
        metadata: dict[str, Any],
        user: UserModel | None = None,
        tenant_id: str | None = None,
    ) -> TemplateModel:
        """Create a template from a zip file. Zip must contain at least one .bpmn file."""
        if user is None:
            raise ApiError("unauthorized", "User must be authenticated", status_code=403)
        tenant = tenant_id or getattr(g, "m8flow_tenant_id", None)
        if tenant is None:
            raise ApiError("tenant_required", TENANT_REQUIRED_MESSAGE, status_code=400)
        template_key = metadata.get("template_key")
        name = metadata.get("name")
        if not template_key or not name:
            raise ApiError("missing_fields", "template_key and name are required", status_code=400)

        # Validate zip size before extracting
        if len(zip_bytes) > MAX_ZIP_SIZE:
            raise ApiError(
                "payload_too_large",
                f"Zip file exceeds maximum allowed size of {MAX_ZIP_SIZE // (1024 * 1024)} MB",
                status_code=400,
            )

        version = metadata.get("version") or cls._next_version(template_key, tenant)
        files_to_add: list[tuple[str, bytes]] = []
        has_bpmn = False
        total_extracted = 0
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                entries = [n for n in zf.namelist() if not n.endswith("/")]
                if len(entries) > MAX_ZIP_ENTRIES:
                    raise ApiError(
                        "payload_too_large",
                        f"Zip contains too many entries (max {MAX_ZIP_ENTRIES})",
                        status_code=400,
                    )
                for name_in_zip in entries:
                    base_name = os.path.basename(name_in_zip)
                    if not base_name:
                        continue
                    if base_name.startswith("."):
                        continue
                    content = zf.read(name_in_zip)
                    total_extracted += len(content)
                    if total_extracted > MAX_EXTRACTED_SIZE:
                        raise ApiError(
                            "payload_too_large",
                            f"Extracted content exceeds maximum allowed size of {MAX_EXTRACTED_SIZE // (1024 * 1024)} MB",
                            status_code=400,
                        )
                    ft = file_type_from_filename(base_name)
                    if ft == "bpmn":
                        has_bpmn = True
                    files_to_add.append((base_name, content))
        except zipfile.BadZipFile as e:
            raise ApiError("invalid_content", f"Invalid zip file: {e}", status_code=400)

        if not has_bpmn:
            raise ApiError("missing_fields", "Zip must contain at least one .bpmn file", status_code=400)

        metadata["version"] = version
        return cls.create_template_with_files(
            metadata=metadata,
            files=files_to_add,
            user=user,
            tenant_id=tenant,
        )

    @classmethod
    def create_process_model_from_template(
        cls,
        template_id: int,
        process_group_id: str,
        process_model_id: str,
        display_name: str,
        description: str | None,
        user: UserModel | None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a process model from a template, copying all files.

        Args:
            template_id: The database ID of the template to use
            process_group_id: The process group where the model will be created
            process_model_id: The ID for the new process model (just the model name, not full path)
            display_name: Display name for the new process model
            description: Optional description for the new process model
            user: The user creating the process model
            tenant_id: Optional tenant ID (defaults to current tenant from context)

        Returns:
            Dictionary containing process_model info and template_info
        """
        if user is None:
            raise ApiError("unauthorized", "User must be authenticated", status_code=403)

        tenant = tenant_id or getattr(g, "m8flow_tenant_id", None)
        if tenant is None:
            raise ApiError("tenant_required", TENANT_REQUIRED_MESSAGE, status_code=400)

        # Get the template
        template = cls.get_template_by_id(template_id, user=user)
        if template is None:
            raise ApiError("not_found", "Template not found", status_code=404)

        # Validate template has files
        if not template.files:
            raise ApiError("invalid_template", "Template has no files", status_code=400)

        # Construct full process model identifier
        full_process_model_id = f"{process_group_id}/{process_model_id}"

        # Validate process group exists
        if not ProcessModelService.is_process_group_identifier(process_group_id):
            raise ApiError(
                "process_group_not_found",
                f"Process group '{process_group_id}' does not exist",
                status_code=404,
            )

        # Check if process model already exists
        if ProcessModelService.is_process_model_identifier(full_process_model_id):
            raise ApiError(
                "process_model_exists",
                f"Process model '{full_process_model_id}' already exists",
                status_code=409,
            )

        # Check if a process group with this ID exists
        if ProcessModelService.is_process_group_identifier(full_process_model_id):
            raise ApiError(
                "process_group_exists",
                f"A process group with ID '{full_process_model_id}' already exists",
                status_code=409,
            )

        # Create the process model
        process_model_info = ProcessModelInfo(
            id=full_process_model_id,
            display_name=display_name,
            description=description or "",
        )
        ProcessModelService.add_process_model(process_model_info)

        # Copy template files to the process model
        primary_file_name = None
        primary_process_id = None
        files_copied = 0

        logger.info(f"Copying {len(template.files)} files from template {template_id} to process model {full_process_model_id}")

        for file_entry in template.files:
            file_name = file_entry.get("file_name")
            file_type = file_entry.get("file_type")

            if not file_name:
                logger.warning(f"Skipping file entry with no file_name: {file_entry}")
                continue

            logger.debug(f"Copying file: {file_name} (type: {file_type})")

            try:
                content = cls.get_file_content(template, file_name)
                logger.debug(f"Retrieved {len(content)} bytes for {file_name}")
            except ApiError as e:
                logger.error(f"Failed to get file content for {file_name} from template {template_id}: {e.message}")
                raise ApiError(
                    "file_copy_failed",
                    f"Failed to copy file '{file_name}' from template: {e.message}",
                    status_code=500,
                )
            except Exception as e:
                logger.error(f"Unexpected error getting file {file_name}: {str(e)}")
                raise ApiError(
                    "file_copy_failed",
                    f"Failed to copy file '{file_name}' from template: {str(e)}",
                    status_code=500,
                )

            # For BPMN files, we need to replace process IDs to make them unique
            if file_type == "bpmn":
                content, new_process_id = cls._transform_bpmn_content(
                    content, process_model_id
                )
                if primary_file_name is None:
                    primary_file_name = file_name
                    primary_process_id = new_process_id

            # Write the file to the process model
            try:
                SpecFileService.update_file(process_model_info, file_name, content)
                files_copied += 1
                logger.debug(f"Successfully wrote file {file_name} to process model")
            except Exception as e:
                logger.error(f"Failed to write file {file_name} to process model: {str(e)}")
                raise ApiError(
                    "file_write_failed",
                    f"Failed to write file '{file_name}' to process model: {str(e)}",
                    status_code=500,
                )

        # Ensure at least one file was copied
        if files_copied == 0:
            raise ApiError(
                "no_files_copied",
                "No files could be copied from the template",
                status_code=500,
            )

        logger.info(f"Successfully copied {files_copied} files to process model {full_process_model_id}")

        # Update process model with primary file info
        if primary_file_name:
            process_model_info.primary_file_name = primary_file_name
        if primary_process_id:
            process_model_info.primary_process_id = primary_process_id
        ProcessModelService.save_process_model(process_model_info)

        # Record the template provenance
        username = user.username if hasattr(user, "username") else "unknown"
        provenance = ProcessModelTemplateModel(
            process_model_identifier=full_process_model_id,
            source_template_id=template.id,
            source_template_key=template.template_key,
            source_template_version=template.version,
            source_template_name=template.name,
            m8f_tenant_id=tenant,
            created_by=username,
        )
        db.session.add(provenance)
        ProcessModelTemplateModel.commit_with_rollback_on_exception()

        # Commit to git
        _commit_and_push_to_git(
            f"User: {username} created process model {full_process_model_id} from template {template.template_key} v{template.version}"
        )

        return {
            "process_model": process_model_info.to_dict(),
            "template_info": provenance.serialized(),
        }

    @classmethod
    def _transform_bpmn_content(
        cls,
        content: bytes,
        process_model_id: str,
    ) -> tuple[bytes, str | None]:
        """Transform BPMN content by replacing process IDs with unique ones.

        Args:
            content: The original BPMN file content
            process_model_id: The process model ID to use as base for new process IDs

        Returns:
            Tuple of (transformed content, new primary process ID)
        """
        try:
            content_str = content.decode("utf-8")
        except UnicodeDecodeError:
            return content, None

        # Generate a unique suffix
        fuzz = "".join(random.SystemRandom().choice(string.ascii_lowercase + string.digits) for _ in range(7))

        # Convert dashes to underscores for process id
        underscored_id = process_model_id.replace("-", "_")

        # Find all process IDs in the BPMN
        # Pattern matches: id="Process_xxx" or id="process_xxx"
        process_id_pattern = re.compile(r'(<bpmn:process[^>]*\s+id=")([^"]+)(")')

        new_primary_process_id = None
        process_counter = 0

        def replace_process_id(match: re.Match) -> str:
            nonlocal new_primary_process_id, process_counter
            prefix = match.group(1)
            suffix = match.group(3)

            # Create new unique process ID with counter for uniqueness
            if process_counter == 0:
                new_id = f"Process_{underscored_id}_{fuzz}"
            else:
                new_id = f"Process_{underscored_id}_{fuzz}_{process_counter}"

            process_counter += 1

            if new_primary_process_id is None:
                new_primary_process_id = new_id

            return f"{prefix}{new_id}{suffix}"

        # Replace process IDs
        content_str = process_id_pattern.sub(replace_process_id, content_str)

        return content_str.encode("utf-8"), new_primary_process_id

    @classmethod
    def get_process_model_template_info(
        cls,
        process_model_identifier: str,
        tenant_id: str | None = None,
    ) -> ProcessModelTemplateModel | None:
        """Get the template provenance info for a process model.

        Args:
            process_model_identifier: The process model identifier
            tenant_id: Optional tenant ID (defaults to current tenant from context)

        Returns:
            ProcessModelTemplateModel if the process model was created from a template, None otherwise
        """
        tenant = tenant_id or getattr(g, "m8flow_tenant_id", None)

        query = ProcessModelTemplateModel.query.filter_by(
            process_model_identifier=process_model_identifier
        )

        if tenant:
            query = query.filter_by(m8f_tenant_id=tenant)

        return query.first()
