"""Zero-heavy-dependency active-tenant primitives: the request/ContextVar
plumbing and shared constants.

Deliberately a leaf module (only stdlib + flask). ``scheduler``, ``workflow``,
and ``services`` import ONLY this module for tenant-context reads, not the
rest of ``auth``, so they are not coupled to auth's Keycloak-client import
graph. See the active-tenant deep-module map, ticket 02.
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar, Token
from typing import Optional, cast

from flask import g, has_request_context

LOGGER = logging.getLogger(__name__)

# JWT claim name used to resolve tenant id. From M8FLOW_TENANT_CLAIM.
TENANT_CLAIM = (os.getenv("M8FLOW_TENANT_CLAIM") or "").strip() or "m8flow_tenant_id"

# Cookie used during shared-realm login flows to preserve the selected tenant
# across auth redirects and expired-session retries. Authoritative for active
# tenant (AGENTS.md) -- frontend localStorage is not tenant finalization.
SELECTED_TENANT_COOKIE_NAME = "m8flow_selected_tenant"

# Optional request header for an explicit tenant when the caller belongs to it.
# Distinct from the active-tenant cookie and from the super-admin tenantId query.
TENANT_SELECTION_HEADER_NAME = "x-m8flow-tenant-id"

_CONTEXT_TENANT_ID: ContextVar[Optional[str]] = ContextVar("m8flow_tenant_id", default=None)

# "Are we inside a request handler?" (works for ASGI/WSGI alike)
_REQUEST_ACTIVE: ContextVar[bool] = ContextVar("m8flow_request_active", default=False)


class TenantContextFilter(logging.Filter):
    """Injects tenant id into log records for uvicorn-log.yaml."""

    def filter(self, record: logging.LogRecord) -> bool:
        tenant_id = _CONTEXT_TENANT_ID.get()
        if not tenant_id and has_request_context():
            tenant_id = getattr(g, "m8flow_tenant_id", None)
        record.m8flow_tenant_id = tenant_id or "-"
        return True


def begin_request_context() -> Token:
    """Mark the current execution context as handling an HTTP request."""
    return _REQUEST_ACTIVE.set(True)


def end_request_context(token: Token) -> None:
    _REQUEST_ACTIVE.reset(token)


def is_request_active() -> bool:
    return _REQUEST_ACTIVE.get()


def set_context_tenant_id(tenant_id: str | None) -> Token:
    return _CONTEXT_TENANT_ID.set(tenant_id)


def reset_context_tenant_id(token: Token) -> None:
    _CONTEXT_TENANT_ID.reset(token)


def get_context_tenant_id() -> str | None:
    return _CONTEXT_TENANT_ID.get()


def is_legacy_placeholder_tenant_id(tenant_id: object) -> bool:
    """Return whether a tenant id is the legacy pre-scoping placeholder."""
    if not isinstance(tenant_id, str):
        return False
    return tenant_id.strip() == "default"


def is_concrete_tenant_id(tenant_id: object) -> bool:
    """Return whether a tenant id represents a concrete tenant context."""
    if not isinstance(tenant_id, str):
        return False

    normalized_tenant_id = tenant_id.strip()
    if not normalized_tenant_id:
        return False

    # Older migrations and requests carrying a stale request context from before
    # the current contextvar-based tenant wiring can still surface the legacy
    # placeholder value "default". Treat it the same as "public": not a usable
    # tenant-scoped runtime identifier.
    return not is_legacy_placeholder_tenant_id(normalized_tenant_id) and normalized_tenant_id != "public"


def clear_tenant_context() -> None:
    """Clear tenant context variables to prevent cross-request leakage."""
    _CONTEXT_TENANT_ID.set(None)
    if has_request_context():
        for flag in (
            "_m8flow_global_request",
            "_m8flow_public_request",
            "_m8flow_tenant_context_exempt_request",
        ):
            if hasattr(g, flag):
                setattr(g, flag, False)


def tenant_id_from_selected_cookie() -> str | None:
    """Read the selected-tenant cookie, or an already-resolved g.m8flow_tenant_id.
    The one place this lookup happens -- route-level tenant helpers should build
    on this instead of re-reading the cookie themselves.
    """
    from flask import request

    return request.cookies.get(SELECTED_TENANT_COOKIE_NAME) or getattr(g, "m8flow_tenant_id", None)


def tenant_override_for_super_admin(*, is_super_admin: bool) -> str | None:
    """Optional cross-tenant scope override: `tenantId` or `tenant_id` query param
    (both spellings m8flow-frontend/m8flow-designer send), honored only for
    super-admins."""
    if not is_super_admin:
        return None
    from flask import request

    return request.args.get("tenantId") or request.args.get("tenant_id") or None


def get_tenant_id(*, warn_on_default: bool = True) -> str:
    """
    Return the tenant id for the current execution.

    ``warn_on_default`` is retained for compatibility with older call sites but
    no implicit default-tenant fallback remains.
    """
    if has_request_context():
        tid = cast(Optional[str], getattr(g, "m8flow_tenant_id", None))
        if tid:
            if get_context_tenant_id() != tid:
                _CONTEXT_TENANT_ID.set(tid)
            return tid

        ctx_tid = get_context_tenant_id()
        if ctx_tid:
            g.m8flow_tenant_id = ctx_tid
            return ctx_tid

        raise RuntimeError("Missing tenant id in request context.")

    # Non-request context
    ctx_tid = get_context_tenant_id()
    if ctx_tid:
        return ctx_tid

    raise RuntimeError("Missing tenant id in non-request context.")
