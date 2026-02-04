# extensions/m8flow-backend/src/m8flow_backend/services/file_system_service_patch.py
from __future__ import annotations
import os
from typing import Any, Dict, Optional
from flask import current_app, g, has_request_context
from m8flow_backend.tenancy import (
    DEFAULT_TENANT_ID,
    allow_missing_tenant_context,
    get_context_tenant_id,
    is_public_request,
)

_ORIGINALS: Dict[str, Any] = {}
_PATCHED = False

def _get_tenant_id() -> str:
    """Get the current tenant id from context."""
    if is_public_request():
        tid: Optional[str] = getattr(g, "m8flow_tenant_id", None)
        if tid:
            return tid
        if allow_missing_tenant_context():
            return DEFAULT_TENANT_ID
        raise RuntimeError("Missing tenant id in request context.")

    # 1) HTTP request path: must be set by middleware (strict)
    if has_request_context():
        tid: Optional[str] = getattr(g, "m8flow_tenant_id", None)
        if tid:
            return tid
        if allow_missing_tenant_context():
            return DEFAULT_TENANT_ID
        raise RuntimeError("Missing tenant id in request context.")

    # 2) Non-request path (Celery/CLI): use ContextVar if present
    tid = get_context_tenant_id()
    if tid:
        return tid

    if allow_missing_tenant_context():
        return DEFAULT_TENANT_ID

    raise RuntimeError("Missing tenant id in non-request context.")



def _tenant_bpmn_root(base_dir: str) -> str:
    """Get tenant-specific BPMN root directory."""
    tenant_id = _get_tenant_id()

    # keep your safety checks here (the tests expect "Unsafe tenant id")
    if (
        not tenant_id
        or ".." in tenant_id
        or "/" in tenant_id
        or "\\" in tenant_id
    ):
        raise RuntimeError("Unsafe tenant id")

    normalized = os.path.abspath(os.path.normpath(base_dir))
    if os.path.basename(normalized) == tenant_id:
        return normalized
    return os.path.join(normalized, tenant_id)



def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.services.file_system_service import FileSystemService

    _ORIGINALS["root_path"] = FileSystemService.root_path

    def patched_root_path() -> str:
        base_dir = current_app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"]
        return _tenant_bpmn_root(base_dir)

    FileSystemService.root_path = staticmethod(patched_root_path)  # type: ignore[assignment]

    _PATCHED = True

