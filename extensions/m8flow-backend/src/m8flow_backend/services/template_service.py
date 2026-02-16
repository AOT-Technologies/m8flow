from __future__ import annotations

import io
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Any

from flask import g
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.user import UserModel

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
            raise ApiError("tenant_required", "Tenant context required", status_code=400)

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

        # Published: create new version and copy files
        next_version = cls._next_version(key, tenant)
        new_files: list[dict] = []
        replaced_first_bpmn = False  # used when bpmn_file_name is not set (backward compat)
        for entry in (existing_template.files or []):
            fname = entry.get("file_name")
            if not fname:
                continue
            try:
                content = cls.storage.get_file(tenant, key, existing_template.version, fname)
                if bpmn_bytes is not None and entry.get("file_type") == "bpmn":
                    if bpmn_file_name and fname == bpmn_file_name:
                        content = bpmn_bytes
                    elif not bpmn_file_name and not replaced_first_bpmn:
                        content = bpmn_bytes
                        replaced_first_bpmn = True
                ft = entry.get("file_type", file_type_from_filename(fname))
                cls.storage.store_file(tenant, key, next_version, fname, ft, content)
                new_files.append({"file_type": ft, "file_name": fname})
            except ApiError as e:
                logger.warning("Failed to copy file %s for new version %s: %s", fname, next_version, e)
        if bpmn_bytes is not None and not any(e.get("file_type") == "bpmn" for e in (existing_template.files or [])):
            add_name = bpmn_file_name or "diagram.bpmn"
            cls.storage.store_file(tenant, key, next_version, add_name, "bpmn", bpmn_bytes)
            new_files.append({"file_type": "bpmn", "file_name": add_name})
        if not new_files:
            raise ApiError(
                "storage_error",
                "Failed to copy any files for the new template version",
                status_code=500,
            )

        new_template = TemplateModel(
            template_key=key,
            version=next_version,
            name=existing_template.name,
            description=existing_template.description,
            tags=existing_template.tags,
            category=existing_template.category,
            m8f_tenant_id=existing_template.m8f_tenant_id,
            visibility=existing_template.visibility,
            files=new_files,
            is_published=False,
            status="draft",
            created_by=username_str,
            modified_by=username_str,
        )
        for field in allowed_fields:
            if field == "status":
                continue  # keep new version as draft, do not overwrite from updates
            if field in updates:
                setattr(new_template, field, updates[field])
        try:
            db.session.add(new_template)
            TemplateModel.commit_with_rollback_on_exception()
        except IntegrityError:
            db.session.rollback()
            raise ApiError(
                error_code="template_conflict",
                message="A template with this key and version already exists for this tenant.",
                status_code=409,
            )
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
    ) -> None:
        """Update content of an existing file. Template must not be published."""
        if template.is_published:
            raise ApiError(
                "forbidden",
                "Cannot update files of a published template",
                status_code=403,
            )
        found = None
        for e in template.files or []:
            if e.get("file_name") == file_name:
                found = e
                break
        if not found:
            raise ApiError("not_found", f"File not found: {file_name}", status_code=404)
        ft = found.get("file_type") or file_type_from_filename(file_name)
        cls.storage.store_file(
            template.m8f_tenant_id,
            template.template_key,
            template.version,
            file_name,
            ft,
            content,
        )

        # Update modified_by if user provided
        if user and hasattr(user, "username"):
            template.modified_by = user.username
            template.modified_at = datetime.now(timezone.utc)
            TemplateModel.commit_with_rollback_on_exception()

    @classmethod
    def delete_file_from_template(
        cls,
        template: TemplateModel,
        file_name: str,
        user: UserModel | None = None,
    ) -> None:
        """Remove a file from the template. Template must not be published. Cannot delete last file or only BPMN."""
        if template.is_published:
            raise ApiError(
                "forbidden",
                "Cannot delete files from a published template",
                status_code=403,
            )
        files_list = list(template.files or [])
        if not files_list:
            raise ApiError("not_found", "Template has no files", status_code=404)
        remaining = [e for e in files_list if e.get("file_name") != file_name]
        if len(remaining) == len(files_list):
            raise ApiError("not_found", f"File not found: {file_name}", status_code=404)
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
        template.files = remaining
        if user and hasattr(user, "username"):
            template.modified_by = user.username
        template.modified_at = datetime.now(timezone.utc)
        TemplateModel.commit_with_rollback_on_exception()
        try:
            cls.storage.delete_file(
                template.m8f_tenant_id,
                template.template_key,
                template.version,
                file_name,
            )
        except Exception:
            pass

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
            raise ApiError("tenant_required", "Tenant context required", status_code=400)
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
