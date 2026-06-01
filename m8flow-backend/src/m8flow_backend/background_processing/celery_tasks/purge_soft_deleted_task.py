"""Celery beat task for periodic purging of soft-deleted process models/groups."""
from __future__ import annotations

import logging
import os

from celery import shared_task

from m8flow_backend import config

logger = logging.getLogger("m8flow.purge_soft_deleted_task")

M8FLOW_CELERY_TASK_PURGE_SOFT_DELETED = (
    "m8flow_backend.background_processing.celery_tasks.purge_soft_deleted_task.celery_task_purge_soft_deleted"
)


@shared_task(name=M8FLOW_CELERY_TASK_PURGE_SOFT_DELETED, ignore_result=True)
def celery_task_purge_soft_deleted() -> None:
    """Purge expired soft-deleted items. Runs daily via Celery beat if enabled."""
    if not os.environ.get("M8FLOW_SOFT_DELETE_PURGE_ENABLED", "").lower() in ("true", "1", "yes"):
        logger.info("Soft-delete purge task skipped (M8FLOW_SOFT_DELETE_PURGE_ENABLED not set)")
        return

    retention_days = config.soft_delete_retention_days()
    retention_seconds = retention_days * 86400

    logger.info("Running scheduled purge with retention_days=%d", retention_days)

    from m8flow_backend.services.soft_delete_service import SoftDeleteService

    summary = SoftDeleteService.purge_expired(retention_seconds, dry_run=False)
    logger.info("Scheduled purge complete: %s", summary)
    if summary.get("errors"):
        logger.error("Errors during scheduled purge: %s", summary["errors"])
