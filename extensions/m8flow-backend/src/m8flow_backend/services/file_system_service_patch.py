# extensions/m8flow-backend/src/m8flow_backend/services/file_system_service_patch.py
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from flask import has_request_context, g

from spiffworkflow_backend.exceptions.api_error import ApiError

_ORIGINALS: Dict[str, Any] = {}
_PATCHED = False

LOGGER = logging.getLogger(__name__)
DEFAULT_TENANT_ID = "default"

def _get_tenant_id() -> str:
    """Return tenant id for the current request, or a fallback for non-request contexts."""
    tid: Optional[str] = getattr(g, "m8flow_tenant_id", None) if has_request_context() else None
    if not tid or tid == "" :
        # TODO:raise error when tenant context auth is implemented
        LOGGER.warning("No tenant id found in request context; using default tenant id.")
        return DEFAULT_TENANT_ID
        # raise ApiError("missing_tenant_id", "Tenant id is required.", status_code=400)
    return tid
    

def _tenant_bpmn_root(base_dir: str) -> str:
    """Return the BPMN spec root path scoped to the current request tenant."""
    tenant_id = _get_tenant_id()

    normalized = os.path.abspath(os.path.normpath(base_dir))
    if os.path.basename(normalized) == tenant_id:
        return normalized

    LOGGER.info("Scoping BPMN spec storage to tenant '%s'", tenant_id)
    return os.path.join(normalized, tenant_id)


def apply() -> None:
    """Patch FileSystemService.root_path to scope BPMN spec storage under a tenant folder."""
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.services.file_system_service import FileSystemService

    _ORIGINALS["root_path"] = FileSystemService.root_path

    def patched_root_path() -> str:
        base_dir = _ORIGINALS["root_path"]()
        return _tenant_bpmn_root(base_dir)

    FileSystemService.root_path = staticmethod(patched_root_path)
    _PATCHED = True
