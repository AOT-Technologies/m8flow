from __future__ import annotations

import logging
import os
from typing import Optional

from flask import g, has_request_context

LOGGER = logging.getLogger(__name__)
DEFAULT_TENANT_ID = os.getenv("M8FLOW_DEFAULT_TENANT_ID", "default")


def get_tenant_id() -> str:
    """Return tenant id for the current request, or a fallback for non-request contexts."""
    tid: Optional[str] = getattr(g, "m8flow_tenant_id", None) if has_request_context() else None
    if not tid:
        # TODO: raise 400 once tenant context auth is implemented.
        LOGGER.warning("No tenant id found in request context; using default tenant id.")
        return DEFAULT_TENANT_ID
    return tid


def ensure_tenant_exists(tenant_id: str) -> None:
    """Ensure the tenant row exists for the given id."""
    if not tenant_id:
        return

    from sqlalchemy.exc import IntegrityError

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from spiffworkflow_backend.models.db import db

    if db.session.get(M8flowTenantModel, tenant_id) is not None:
        return

    db.session.add(M8flowTenantModel(id=tenant_id, name=tenant_id))
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        if db.session.get(M8flowTenantModel, tenant_id) is None:
            raise
