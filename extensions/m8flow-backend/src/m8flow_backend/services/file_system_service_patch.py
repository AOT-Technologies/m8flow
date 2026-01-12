# extensions/m8flow-backend/src/m8flow_backend/services/file_system_service_patch.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from flask import has_request_context, g

_ORIGINALS: Dict[str, Any] = {}
_PATCHED = False

DEFAULT_TENANT_ID = "default"


def _get_tenant_id() -> str:
    """Return tenant id for the current request, or a fallback for non-request contexts."""
    if has_request_context():
        tid: Optional[str] = getattr(g, "m8flow_tenant_id", None)
        if tid:
            return tid
        # TODO instead of defaulting, raise ApiError here.
        return DEFAULT_TENANT_ID
    return DEFAULT_TENANT_ID


def _tenant_bpmn_root(base_dir: str) -> str:
    tenant_id = _get_tenant_id()

    normalized = os.path.abspath(os.path.normpath(base_dir))
    if os.path.basename(normalized) == tenant_id:
        return normalized

    # Optional debug
    print(f"Scoping BPMN spec storage to tenant '{tenant_id}'")
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
