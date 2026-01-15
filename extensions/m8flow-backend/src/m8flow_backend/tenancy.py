from __future__ import annotations
import os
import logging
from typing import Optional

from flask import g, has_request_context

LOGGER = logging.getLogger(__name__)
# Default tenant used when no request context is available.
# This must exist in the database before runtime/migrations that backfill tenant ids.
DEFAULT_TENANT_ID = os.getenv("M8FLOW_DEFAULT_TENANT_ID", "default")


def get_tenant_id() -> str:
    """Return tenant id for the current request, or a fallback for non-request contexts."""
    tid: Optional[str] = getattr(g, "m8flow_tenant_id", None) if has_request_context() else None
    if not tid:
        # TODO: raise 400 once tenant context auth is implemented.
        LOGGER.warning("No tenant id found in request context; using default tenant id.")
        return DEFAULT_TENANT_ID
    return tid


def ensure_tenant_exists(tenant_id: str | None) -> None:
    """Validate that the tenant row exists; raise if missing to enforce pre-provisioning."""
    if not tenant_id:
        raise RuntimeError(
            "Missing tenant id. Provide the M8Flow-Tenant-Id header (or set it in request context)."
        )

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from spiffworkflow_backend.models.db import db

    if db.session.get(M8flowTenantModel, tenant_id) is None:
        raise RuntimeError(
            f"Tenant '{tenant_id}' does not exist. Create it in m8flow_tenant before using M8Flow."
        )
