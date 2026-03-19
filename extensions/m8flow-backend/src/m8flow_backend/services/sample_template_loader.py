"""Load sample template ZIP files into the database at startup.

Scans the ``sample_templates/`` directory for ``.zip`` files, extracts them,
and inserts a ``TemplateModel`` row per ZIP.  Templates are created as
**public** and **published** under the default tenant with ``created_by=system``.

Duplicate detection: if a template with the same ``template_key`` already
exists for the target tenant, it is silently skipped.
"""
from __future__ import annotations

import io
import logging
import os
import pathlib
import zipfile

from flask import Flask
from sqlalchemy.exc import IntegrityError

from spiffworkflow_backend.models.db import db

from m8flow_backend.models.template import TemplateModel, TemplateVisibility
from m8flow_backend.services.template_storage_service import (
    FilesystemTemplateStorageService,
    file_type_from_filename,
)
from m8flow_backend.tenancy import DEFAULT_TENANT_ID, create_tenant_if_not_exists

logger = logging.getLogger(__name__)

SAMPLE_TEMPLATES_DIR = pathlib.Path(__file__).resolve().parents[3] / "sample_templates"

SYSTEM_USER = "system"
VERSION = "V1"


def _title_from_key(template_key: str) -> str:
    """Convert ``some-template-key`` to ``Some Template Key``."""
    return template_key.replace("-", " ").replace("_", " ").title()


def _extract_zip(zip_bytes: bytes) -> list[tuple[str, bytes]]:
    """Return ``[(file_name, content), ...]`` from a ZIP, skipping directories and dotfiles."""
    files: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            base = os.path.basename(name)
            if not base or base.startswith("."):
                continue
            files.append((base, zf.read(name)))
    return files


def load_sample_templates(app: Flask, *, sample_dir: pathlib.Path | None = None) -> int:
    """Load all ``.zip`` templates from *sample_dir* into the database.

    Returns the number of templates actually inserted (skips duplicates).
    """
    sample_dir = sample_dir or SAMPLE_TEMPLATES_DIR
    if not sample_dir.is_dir():
        logger.warning("Sample templates directory not found: %s", sample_dir)
        return 0

    zip_files = sorted(p for p in sample_dir.iterdir() if p.suffix.lower() == ".zip")
    if not zip_files:
        logger.info("No .zip files found in %s – nothing to load.", sample_dir)
        return 0

    tenant_id = DEFAULT_TENANT_ID
    storage = FilesystemTemplateStorageService()

    with app.app_context():
        create_tenant_if_not_exists(tenant_id)

        loaded = 0
        for zip_path in zip_files:
            template_key = zip_path.stem
            name = _title_from_key(template_key)

            existing = (
                TemplateModel.query
                .filter_by(template_key=template_key, m8f_tenant_id=tenant_id)
                .first()
            )
            if existing is not None:
                logger.info(
                    "Sample template '%s' already exists for tenant '%s' – skipping.",
                    template_key,
                    tenant_id,
                )
                continue

            zip_bytes = zip_path.read_bytes()
            try:
                files = _extract_zip(zip_bytes)
            except zipfile.BadZipFile:
                logger.error("Invalid ZIP file, skipping: %s", zip_path)
                continue

            has_bpmn = any(file_type_from_filename(fn) == "bpmn" for fn, _ in files)
            if not has_bpmn:
                logger.warning("ZIP has no .bpmn file, skipping: %s", zip_path)
                continue

            file_entries: list[dict] = []
            for file_name, content in files:
                ft = file_type_from_filename(file_name)
                storage.store_file(tenant_id, template_key, VERSION, file_name, ft, content)
                file_entries.append({"file_type": ft, "file_name": file_name})

            template = TemplateModel(
                template_key=template_key,
                version=VERSION,
                name=name,
                description=None,
                tags=None,
                category=None,
                m8f_tenant_id=tenant_id,
                visibility=TemplateVisibility.public.value,
                files=file_entries,
                is_published=True,
                status="published",
                is_deleted=False,
                created_by=SYSTEM_USER,
                modified_by=SYSTEM_USER,
            )

            try:
                db.session.add(template)
                db.session.commit()
                loaded += 1
                logger.info("Loaded sample template '%s' (tenant=%s).", template_key, tenant_id)
            except IntegrityError:
                db.session.rollback()
                logger.info(
                    "Sample template '%s' already exists (caught by constraint) – skipping.",
                    template_key,
                )

    logger.info("Sample template loading complete: %d loaded, %d total ZIPs.", loaded, len(zip_files))
    return loaded


def load_sample_templates_if_enabled(app: Flask) -> None:
    """Check the ``M8FLOW_LOAD_SAMPLE_TEMPLATES`` env var and load if truthy."""
    value = os.getenv("M8FLOW_LOAD_SAMPLE_TEMPLATES", "false").strip().lower()
    if value not in ("1", "true", "yes", "on"):
        return
    logger.info("M8FLOW_LOAD_SAMPLE_TEMPLATES is enabled – loading sample templates.")
    load_sample_templates(app)
