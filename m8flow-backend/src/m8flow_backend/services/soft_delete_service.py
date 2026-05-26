"""Service for soft-deleting and restoring process models and process groups."""
from __future__ import annotations

import logging
import os
import re
import shutil
import time
from typing import Any

from flask import current_app, g

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.services.file_system_service import FileSystemService

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.models.process_model_deletion import DeletionStatus, ProcessModelDeletionModel
from m8flow_backend.models.process_group_deletion import ProcessGroupDeletionModel
from m8flow_backend.tenancy import set_context_tenant_id, reset_context_tenant_id

logger = logging.getLogger("m8flow.soft_delete")

SOFT_DELETED_PATTERN = re.compile(r"^.+_deleted_\d{10}$")


class OriginalIdentifierUnavailableError(Exception):
    pass


class SoftDeleteService:

    @classmethod
    def soft_delete_process_model(cls, process_model_id: str, user: Any) -> ProcessModelDeletionModel:
        from spiffworkflow_backend.services.process_model_service import ProcessModelService
        from spiffworkflow_backend.routes.process_api_blueprint import _commit_and_push_to_git

        process_model = ProcessModelService.get_process_model(process_model_id)
        display_name = process_model.display_name or process_model_id.split("/")[-1]

        parent_parts = process_model_id.rsplit("/", 1)
        parent_group_id = parent_parts[0] if len(parent_parts) > 1 else None
        model_name = parent_parts[-1]

        now = int(time.time())
        new_name = f"{model_name}_deleted_{now}"
        if parent_group_id:
            deleted_identifier = f"{parent_group_id}/{new_name}"
        else:
            deleted_identifier = new_name

        original_path = FileSystemService.full_path_from_id(process_model_id)
        deleted_path = FileSystemService.full_path_from_id(deleted_identifier)

        shutil.move(original_path, deleted_path)

        tenant_id = getattr(g, "m8flow_tenant_id", None) or ""
        username = getattr(user, "username", "system") if user else "system"

        deletion = ProcessModelDeletionModel(
            m8f_tenant_id=tenant_id,
            original_identifier=process_model_id,
            deleted_identifier=deleted_identifier,
            display_name=display_name,
            parent_group_id=parent_group_id,
            status=DeletionStatus.SOFT_DELETED.value,
            deleted_at_in_seconds=now,
            deleted_by=username,
        )
        db.session.add(deletion)
        db.session.commit()

        logger.info(
            "m8flow.soft_delete event=soft_delete_process_model original_identifier=%s "
            "deleted_identifier=%s user=%s tenant=%s",
            process_model_id, deleted_identifier, username, tenant_id,
        )

        try:
            _commit_and_push_to_git(
                f"User: {username} soft-deleted process model {process_model_id} -> {deleted_identifier}"
            )
        except Exception:
            logger.warning("Git commit for soft-delete failed (non-fatal)", exc_info=True)

        return deletion

    @classmethod
    def soft_delete_process_group(cls, process_group_id: str, user: Any) -> ProcessGroupDeletionModel:
        from spiffworkflow_backend.services.process_model_service import ProcessModelService
        from spiffworkflow_backend.routes.process_api_blueprint import _commit_and_push_to_git

        process_group = ProcessModelService.get_process_group(process_group_id, find_direct_nested_items=False)
        display_name = process_group.display_name or process_group_id.split("/")[-1]

        parent_parts = process_group_id.rsplit("/", 1)
        parent_group_id = parent_parts[0] if len(parent_parts) > 1 else None
        group_name = parent_parts[-1]

        now = int(time.time())
        new_name = f"{group_name}_deleted_{now}"
        if parent_group_id:
            deleted_identifier = f"{parent_group_id}/{new_name}"
        else:
            deleted_identifier = new_name

        original_path = FileSystemService.full_path_from_id(process_group_id)
        deleted_path = FileSystemService.full_path_from_id(deleted_identifier)

        shutil.move(original_path, deleted_path)

        tenant_id = getattr(g, "m8flow_tenant_id", None) or ""
        username = getattr(user, "username", "system") if user else "system"

        deletion = ProcessGroupDeletionModel(
            m8f_tenant_id=tenant_id,
            original_identifier=process_group_id,
            deleted_identifier=deleted_identifier,
            display_name=display_name,
            parent_group_id=parent_group_id,
            status=DeletionStatus.SOFT_DELETED.value,
            deleted_at_in_seconds=now,
            deleted_by=username,
        )
        db.session.add(deletion)
        db.session.commit()

        logger.info(
            "m8flow.soft_delete event=soft_delete_process_group original_identifier=%s "
            "deleted_identifier=%s user=%s tenant=%s",
            process_group_id, deleted_identifier, username, tenant_id,
        )

        try:
            _commit_and_push_to_git(
                f"User: {username} soft-deleted process group {process_group_id} -> {deleted_identifier}"
            )
        except Exception:
            logger.warning("Git commit for soft-delete failed (non-fatal)", exc_info=True)

        return deletion

    @classmethod
    def restore_process_model(
        cls,
        deletion_id: int,
        *,
        new_identifier: str | None = None,
        new_display_name: str | None = None,
        user: Any = None,
    ):
        from spiffworkflow_backend.services.process_model_service import ProcessModelService
        from spiffworkflow_backend.routes.process_api_blueprint import _commit_and_push_to_git

        deletion = db.session.execute(
            db.select(ProcessModelDeletionModel).filter_by(id=deletion_id).with_for_update()
        ).scalar_one_or_none()
        if deletion is None:
            raise ApiError("not_found", "Deletion record not found", status_code=404)

        tenant_id = getattr(g, "m8flow_tenant_id", None)
        if tenant_id and deletion.m8f_tenant_id != tenant_id:
            raise ApiError("forbidden", "Access denied to this deletion record", status_code=403)

        if deletion.status != DeletionStatus.SOFT_DELETED.value:
            raise ApiError("invalid_state", "Only soft-deleted items can be restored", status_code=400)

        target_identifier = new_identifier if new_identifier else deletion.original_identifier

        if ProcessModelService.is_process_model_identifier(target_identifier):
            raise OriginalIdentifierUnavailableError(
                f"The identifier '{target_identifier}' is already in use."
            )
        if ProcessModelService.is_process_group_identifier(target_identifier):
            raise OriginalIdentifierUnavailableError(
                f"The identifier '{target_identifier}' is already in use by a process group."
            )

        deleted_path = FileSystemService.full_path_from_id(deletion.deleted_identifier)
        restored_path = FileSystemService.full_path_from_id(target_identifier)

        if not os.path.exists(deleted_path):
            raise ApiError(
                "directory_missing",
                f"Soft-deleted directory no longer exists: {deletion.deleted_identifier}",
                status_code=500,
            )

        parent_id = target_identifier.rsplit("/", 1)[0] if "/" in target_identifier else None
        if parent_id:
            parent_path = FileSystemService.full_path_from_id(parent_id)
            parent_json = os.path.join(parent_path, FileSystemService.PROCESS_GROUP_JSON_FILE)
            if not os.path.isfile(parent_json):
                raise ApiError(
                    "parent_group_missing",
                    f"Parent group '{parent_id}' does not exist or was also deleted. Restore it first.",
                    status_code=409,
                )

        os.makedirs(os.path.dirname(restored_path), exist_ok=True)
        shutil.move(deleted_path, restored_path)

        now = int(time.time())
        username = getattr(user, "username", "system") if user else "system"

        deletion.status = DeletionStatus.RESTORED.value
        deletion.restored_at_in_seconds = now
        deletion.restored_by = username
        deletion.restored_identifier = target_identifier
        db.session.add(deletion)
        db.session.commit()

        logger.info(
            "m8flow.soft_delete event=restore_process_model deletion_id=%s "
            "restored_identifier=%s user=%s",
            deletion_id, target_identifier, username,
        )

        try:
            _commit_and_push_to_git(
                f"User: {username} restored process model {deletion.original_identifier} as {target_identifier}"
            )
        except Exception:
            logger.warning("Git commit for restore failed (non-fatal)", exc_info=True)

        process_model = ProcessModelService.get_process_model(target_identifier)
        if new_display_name:
            process_model.display_name = new_display_name
            ProcessModelService.save_process_model(process_model)

        return process_model

    @classmethod
    def restore_process_group(
        cls,
        deletion_id: int,
        *,
        new_identifier: str | None = None,
        user: Any = None,
    ):
        from spiffworkflow_backend.services.process_model_service import ProcessModelService
        from spiffworkflow_backend.routes.process_api_blueprint import _commit_and_push_to_git

        deletion = db.session.execute(
            db.select(ProcessGroupDeletionModel).filter_by(id=deletion_id).with_for_update()
        ).scalar_one_or_none()
        if deletion is None:
            raise ApiError("not_found", "Deletion record not found", status_code=404)

        tenant_id = getattr(g, "m8flow_tenant_id", None)
        if tenant_id and deletion.m8f_tenant_id != tenant_id:
            raise ApiError("forbidden", "Access denied to this deletion record", status_code=403)

        if deletion.status != DeletionStatus.SOFT_DELETED.value:
            raise ApiError("invalid_state", "Only soft-deleted items can be restored", status_code=400)

        target_identifier = new_identifier if new_identifier else deletion.original_identifier

        if ProcessModelService.is_process_group_identifier(target_identifier):
            raise OriginalIdentifierUnavailableError(
                f"The identifier '{target_identifier}' is already in use."
            )
        if ProcessModelService.is_process_model_identifier(target_identifier):
            raise OriginalIdentifierUnavailableError(
                f"The identifier '{target_identifier}' is already in use by a process model."
            )

        deleted_path = FileSystemService.full_path_from_id(deletion.deleted_identifier)
        restored_path = FileSystemService.full_path_from_id(target_identifier)

        if not os.path.exists(deleted_path):
            raise ApiError(
                "directory_missing",
                f"Soft-deleted directory no longer exists: {deletion.deleted_identifier}",
                status_code=500,
            )

        parent_id = target_identifier.rsplit("/", 1)[0] if "/" in target_identifier else None
        if parent_id:
            parent_path = FileSystemService.full_path_from_id(parent_id)
            parent_json = os.path.join(parent_path, FileSystemService.PROCESS_GROUP_JSON_FILE)
            if not os.path.isfile(parent_json):
                raise ApiError(
                    "parent_group_missing",
                    f"Parent group '{parent_id}' does not exist or was also deleted. Restore it first.",
                    status_code=409,
                )

        os.makedirs(os.path.dirname(restored_path), exist_ok=True)
        shutil.move(deleted_path, restored_path)

        now = int(time.time())
        username = getattr(user, "username", "system") if user else "system"

        deletion.status = DeletionStatus.RESTORED.value
        deletion.restored_at_in_seconds = now
        deletion.restored_by = username
        deletion.restored_identifier = target_identifier
        db.session.add(deletion)
        db.session.commit()

        logger.info(
            "m8flow.soft_delete event=restore_process_group deletion_id=%s "
            "restored_identifier=%s user=%s",
            deletion_id, target_identifier, username,
        )

        try:
            _commit_and_push_to_git(
                f"User: {username} restored process group {deletion.original_identifier} as {target_identifier}"
            )
        except Exception:
            logger.warning("Git commit for restore failed (non-fatal)", exc_info=True)

        return ProcessModelService.get_process_group(target_identifier)

    @classmethod
    def list_deleted_process_models(
        cls,
        tenant_id: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[ProcessModelDeletionModel], dict]:
        query = ProcessModelDeletionModel.query.filter_by(status=DeletionStatus.SOFT_DELETED.value)
        if tenant_id:
            query = query.filter_by(m8f_tenant_id=tenant_id)
        query = query.order_by(ProcessModelDeletionModel.deleted_at_in_seconds.desc())

        total = query.count()
        items = query.offset((page - 1) * per_page).limit(per_page).all()
        pages = (total + per_page - 1) // per_page

        pagination = {"count": len(items), "total": total, "pages": pages, "page": page}
        return items, pagination

    @classmethod
    def list_deleted_process_groups(
        cls,
        tenant_id: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[ProcessGroupDeletionModel], dict]:
        query = ProcessGroupDeletionModel.query.filter_by(status=DeletionStatus.SOFT_DELETED.value)
        if tenant_id:
            query = query.filter_by(m8f_tenant_id=tenant_id)
        query = query.order_by(ProcessGroupDeletionModel.deleted_at_in_seconds.desc())

        total = query.count()
        items = query.offset((page - 1) * per_page).limit(per_page).all()
        pages = (total + per_page - 1) // per_page

        pagination = {"count": len(items), "total": total, "pages": pages, "page": page}
        return items, pagination

    @classmethod
    def purge_single_process_model(cls, deletion_id: int, user: Any = None) -> ProcessModelDeletionModel:
        deletion = db.session.execute(
            db.select(ProcessModelDeletionModel).filter_by(id=deletion_id).with_for_update()
        ).scalar_one_or_none()
        if deletion is None:
            raise ApiError("not_found", "Deletion record not found", status_code=404)

        tenant_id = getattr(g, "m8flow_tenant_id", None)
        if tenant_id and deletion.m8f_tenant_id != tenant_id:
            raise ApiError("forbidden", "Access denied to this deletion record", status_code=403)

        if deletion.status != DeletionStatus.SOFT_DELETED.value:
            raise ApiError("invalid_state", "Only soft-deleted items can be purged", status_code=400)

        deleted_path = FileSystemService.full_path_from_id(deletion.deleted_identifier)
        if os.path.exists(deleted_path):
            shutil.rmtree(deleted_path)

        now = int(time.time())
        username = getattr(user, "username", "system") if user else "system"

        deletion.status = DeletionStatus.PURGED.value
        deletion.purged_at_in_seconds = now
        db.session.add(deletion)
        db.session.commit()

        logger.info(
            "m8flow.soft_delete event=purge_process_model deletion_id=%s "
            "deleted_identifier=%s user=%s",
            deletion_id, deletion.deleted_identifier, username,
        )
        return deletion

    @classmethod
    def purge_expired(cls, retention_seconds: int, *, dry_run: bool = False) -> dict:
        """Permanently delete soft-deleted items older than retention_seconds.

        Iterates all tenants. Returns summary dict of purged counts.
        """
        cutoff = int(time.time()) - retention_seconds
        summary: dict[str, Any] = {"process_models_purged": 0, "process_groups_purged": 0, "errors": []}

        tenants = M8flowTenantModel.query.all()
        for tenant in tenants:
            token = set_context_tenant_id(tenant.id)
            try:
                cls._purge_expired_for_tenant(tenant.id, cutoff, summary, dry_run=dry_run)
            except Exception as exc:
                summary["errors"].append({"tenant_id": tenant.id, "error": str(exc)})
                logger.error("Purge failed for tenant %s: %s", tenant.id, exc, exc_info=True)
            finally:
                reset_context_tenant_id(token)

        logger.info(
            "m8flow.soft_delete event=purge_expired retention_seconds=%s dry_run=%s summary=%s",
            retention_seconds, dry_run, summary,
        )
        return summary

    @classmethod
    def _purge_expired_for_tenant(
        cls, tenant_id: str, cutoff: int, summary: dict, *, dry_run: bool = False
    ) -> None:
        model_deletions = (
            ProcessModelDeletionModel.query
            .filter_by(m8f_tenant_id=tenant_id, status=DeletionStatus.SOFT_DELETED.value)
            .filter(ProcessModelDeletionModel.deleted_at_in_seconds <= cutoff)
            .all()
        )
        for deletion in model_deletions:
            if dry_run:
                summary["process_models_purged"] += 1
                continue
            deleted_path = FileSystemService.full_path_from_id(deletion.deleted_identifier)
            if os.path.exists(deleted_path):
                shutil.rmtree(deleted_path)
            deletion.status = DeletionStatus.PURGED.value
            deletion.purged_at_in_seconds = int(time.time())
            db.session.add(deletion)
            summary["process_models_purged"] += 1
            logger.info(
                "m8flow.soft_delete event=purge_process_model tenant=%s deletion_id=%s identifier=%s",
                tenant_id, deletion.id, deletion.deleted_identifier,
            )

        group_deletions = (
            ProcessGroupDeletionModel.query
            .filter_by(m8f_tenant_id=tenant_id, status=DeletionStatus.SOFT_DELETED.value)
            .filter(ProcessGroupDeletionModel.deleted_at_in_seconds <= cutoff)
            .all()
        )
        for deletion in group_deletions:
            if dry_run:
                summary["process_groups_purged"] += 1
                continue
            deleted_path = FileSystemService.full_path_from_id(deletion.deleted_identifier)
            if os.path.exists(deleted_path):
                shutil.rmtree(deleted_path)
            deletion.status = DeletionStatus.PURGED.value
            deletion.purged_at_in_seconds = int(time.time())
            db.session.add(deletion)
            summary["process_groups_purged"] += 1
            logger.info(
                "m8flow.soft_delete event=purge_process_group tenant=%s deletion_id=%s identifier=%s",
                tenant_id, deletion.id, deletion.deleted_identifier,
            )

        if not dry_run:
            db.session.commit()

    @classmethod
    def is_soft_deleted_identifier(cls, identifier: str) -> bool:
        last_segment = identifier.rsplit("/", 1)[-1]
        return bool(SOFT_DELETED_PATTERN.match(last_segment))
