from __future__ import annotations
import logging
import os
from contextvars import ContextVar
from contextvars import Token
from typing import Optional

from flask import g, has_request_context

LOGGER = logging.getLogger(__name__)
# Default tenant used when no request context is available.
# This must exist in the database before runtime/migrations that backfill tenant ids.
DEFAULT_TENANT_ID = os.getenv("M8FLOW_DEFAULT_TENANT_ID", "default")
# Context variable to hold tenant id for non-request contexts (e.g., background jobs).
# This allows setting and getting tenant id outside of Flask request context.
_CONTEXT_TENANT_ID: ContextVar[Optional[str]] = ContextVar("m8flow_tenant_id", default=None)


def set_context_tenant_id(tenant_id: str | None) -> Token:
    """Set a non-request tenant id for background jobs."""
    return _CONTEXT_TENANT_ID.set(tenant_id)


def reset_context_tenant_id(token: Token) -> None:
    """Reset the non-request tenant id."""
    _CONTEXT_TENANT_ID.reset(token)


def get_context_tenant_id() -> str | None:
    """Return the non-request tenant id, if set."""
    return _CONTEXT_TENANT_ID.get()


def get_tenant_id() -> str:
    """Return tenant id for the current request, or a fallback for non-request contexts."""
    if has_request_context():
        tid: Optional[str] = getattr(g, "m8flow_tenant_id", None)
        if tid:
            return tid
        # TODO: raise 400 once tenant context auth is implemented.
        LOGGER.warning("No tenant id found in request context; using default tenant id.")
        return DEFAULT_TENANT_ID

    # Use the context tenant id for non-request work like background jobs or CLI scripts.
    context_tid = get_context_tenant_id()
    if context_tid:
        return context_tid
    raise RuntimeError("Missing tenant id for non-request context; set it with set_context_tenant_id().")


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


def create_tenant_if_not_exists(tenant_id: str, name: str | None = None) -> None:
    """Create a tenant row if it does not exist (e.g. after creating a Keycloak realm)."""
    if not tenant_id or not tenant_id.strip():
        return
    tenant_id = tenant_id.strip()
    display_name = (name or tenant_id).strip()

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from spiffworkflow_backend.models.db import db

    if db.session.get(M8flowTenantModel, tenant_id) is not None:
        return
    tenant = M8flowTenantModel(id=tenant_id, name=display_name)
    db.session.add(tenant)
    db.session.commit()
    LOGGER.info("Created tenant row for tenant_id=%s name=%s", tenant_id, display_name)
