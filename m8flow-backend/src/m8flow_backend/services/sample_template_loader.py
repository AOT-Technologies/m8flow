"""Load sample template ZIP files into the database at startup.

Controlled by the M8FLOW_LOAD_SAMPLE_TEMPLATES environment variable.
Skips templates that already exist (idempotent).
"""

from __future__ import annotations

import logging
import os
import re

from sqlalchemy.exc import IntegrityError

from m8flow_backend.db import get_session_factory
from m8flow_backend.errors import ApiError

from m8flow_backend.models.template import TemplateModel, TemplateVisibility
from m8flow_backend.services.template_storage_service import (
    FilesystemTemplateStorageService,
    file_type_from_filename,
    safe_extract_zip,
)
from m8flow_backend.startup.shared_realm_bootstrap import resolve_default_shared_realm_tenant_id

logger = logging.getLogger(__name__)

SYSTEM_USER = "system"
VERSION = "V2"
UNIQUE_TEMPLATE_CONSTRAINT = "uq_template_key_version_tenant"

_SAMPLE_TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, os.pardir,
    "sample_templates",
)


def _derive_template_key(filename: str) -> str:
    """Convert a ZIP filename into a stable, URL-safe template key.

    Example: 'approval-with-loop-Content-Review (1).zip' -> 'approval-with-loop-content-review'
    """
    stem = os.path.splitext(filename)[0]
    key = stem.lower()
    key = re.sub(r"\s*\([^)]*\)\s*", "", key)
    key = re.sub(r"[^a-z0-9-]", "-", key)
    key = re.sub(r"-{2,}", "-", key)
    key = key.strip("-")
    return key


def _derive_display_name(filename: str) -> str:
    """Convert a ZIP filename into a human-readable display name.

    Example: 'approval-with-loop-Content-Review (1).zip' -> 'Approval With Loop Content Review'
    """
    stem = os.path.splitext(filename)[0]
    name = re.sub(r"\s*\([^)]*\)\s*", " ", stem)
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name.title()


def _extract_zip(zip_path: str) -> list[tuple[str, bytes]]:
    """Extract files from a ZIP, returning (base_name, content) pairs. Delegates
    to template_storage_service.safe_extract_zip -- the same size/entry-limit
    logic import_template_from_zip uses for uploaded template zips -- and
    translates its ApiError into ValueError so the caller's existing except
    clause still catches it."""
    with open(zip_path, "rb") as fh:
        zip_bytes = fh.read()
    try:
        return safe_extract_zip(zip_bytes)
    except ApiError as exc:
        raise ValueError(exc.message) from exc


def load_sample_templates(flask_app) -> None:  # noqa: ANN001
    """Load sample template ZIPs into the DB if M8FLOW_LOAD_SAMPLE_TEMPLATES is truthy."""
    env_value = os.environ.get("M8FLOW_LOAD_SAMPLE_TEMPLATES", "")
    if env_value.strip().lower() not in ("1", "true", "yes", "on"):
        return

    sample_dir = os.path.normpath(os.path.abspath(_SAMPLE_TEMPLATES_DIR))
    if not os.path.isdir(sample_dir):
        logger.warning("Sample templates directory not found: %s", sample_dir)
        return

    zip_files = sorted(f for f in os.listdir(sample_dir) if f.lower().endswith(".zip"))
    if not zip_files:
        logger.info("No sample template ZIP files found in %s", sample_dir)
        return

    logger.info("Loading sample templates from %s (%d ZIP files) ...", sample_dir, len(zip_files))

    with flask_app.app_context():
        tenant_id = resolve_default_shared_realm_tenant_id()
        if not tenant_id:
            logger.warning("Skipping sample template load; no canonical shared-realm tenant row is available.")
            return

        storage = FilesystemTemplateStorageService()
        loaded = 0
        skipped = 0
        session = get_session_factory()()
        try:
            for zip_filename in zip_files:
                try:
                    template_key = _derive_template_key(zip_filename)
                    display_name = _derive_display_name(zip_filename)

                    if not template_key:
                        logger.warning("Could not derive template key from %s; skipping", zip_filename)
                        skipped += 1
                        continue

                    existing = (
                        session.query(TemplateModel)
                        .filter_by(template_key=template_key, version=VERSION, m8f_tenant_id=tenant_id)
                        .first()
                    )
                    if existing is not None:
                        logger.info("Sample template '%s' already exists; skipping", template_key)
                        skipped += 1
                        continue

                    zip_path = os.path.join(sample_dir, zip_filename)
                    try:
                        files = _extract_zip(zip_path)
                    except ValueError as exc:
                        logger.error("Failed to extract %s: %s", zip_filename, exc)
                        skipped += 1
                        continue

                    has_bpmn = any(file_type_from_filename(name) == "bpmn" for name, _ in files)
                    if not has_bpmn:
                        logger.warning("ZIP %s contains no BPMN file; skipping", zip_filename)
                        skipped += 1
                        continue

                    file_entries: list[dict] = []
                    try:
                        for file_name, content in files:
                            ft = file_type_from_filename(file_name)
                            storage.store_file(tenant_id, template_key, VERSION, file_name, ft, content)
                            file_entries.append({"file_type": ft, "file_name": file_name})
                    except Exception:
                        logger.exception("Failed to store files for %s", zip_filename)
                        skipped += 1
                        continue

                    template = TemplateModel(
                        template_key=template_key,
                        version=VERSION,
                        name=display_name,
                        description=f"Sample template: {display_name}",
                        tags=["sample"],
                        category="Sample",
                        m8f_tenant_id=tenant_id,
                        visibility=TemplateVisibility.public.value,
                        files=file_entries,
                        is_published=True,
                        status="published",
                        created_by=SYSTEM_USER,
                        modified_by=SYSTEM_USER,
                    )

                    try:
                        session.add(template)
                        session.commit()
                        loaded += 1
                        logger.info("Loaded sample template: %s (key=%s)", display_name, template_key)
                    except IntegrityError as exc:
                        session.rollback()
                        err_msg = str(getattr(exc, "orig", exc))
                        if UNIQUE_TEMPLATE_CONSTRAINT in err_msg:
                            logger.info("Sample template '%s' already exists (concurrent); skipping", template_key)
                        else:
                            logger.warning("Failed to insert sample template '%s': %s", template_key, err_msg)
                        skipped += 1

                except Exception:
                    logger.exception("Unexpected error loading sample template %s", zip_filename)
                    skipped += 1
                    continue
        finally:
            session.close()

        logger.info("Sample templates loading complete: %d loaded, %d skipped", loaded, skipped)
