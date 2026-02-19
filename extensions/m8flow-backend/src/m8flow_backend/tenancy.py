# extensions/m8flow-backend/src/m8flow_backend/tenancy.py
from __future__ import annotations

import logging
import os
from contextvars import ContextVar, Token
from typing import Optional, cast

from flask import g, has_request_context

LOGGER = logging.getLogger(__name__)

# Default tenant used when no request context is available.
# This must exist in the database before runtime/migrations that backfill tenant ids.
DEFAULT_TENANT_ID = os.getenv("M8FLOW_DEFAULT_TENANT_ID", "default")

# JWT claim name used to resolve tenant id. From M8FLOW_TENANT_CLAIM.
_raw = (os.getenv("M8FLOW_TENANT_CLAIM") or "m8flow_tenant_id").strip()
TENANT_CLAIM: str = _raw if _raw else "m8flow_tenant_id"

# Include both prefixed and unprefixed paths so we match regardless of SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX.
PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/favicon.ico",
    "/v1.0/status",
    "/status",
    "/v1.0/openapi.json",
    "/openapi.json",
    "/v1.0/openapi.yaml",
    "/openapi.yaml",
    "/v1.0/ui",
    "/ui",
    "/v1.0/static",
    "/static",
    "/v1.0/logout",
    "/logout",
    "/v1.0/authentication-options",
    "/authentication-options",
    "/v1.0/login",
    "/login",
    # Pre-login tenant selection endpoints (must not require tenant context)
    "/v1.0/tenants/check",
    "/tenants/check",
    "/v1.0/m8flow/tenant-login-url",
    "/m8flow/tenant-login-url",
    # Bootstrap/admin: create realm and create tenant (no tenant in token yet)
    "/v1.0/m8flow/tenant-realms",
    "/m8flow/tenant-realms",
    "/v1.0/m8flow/create-tenant",
    "/m8flow/create-tenant",
)

# Path suffixes for pre-login tenant selection (no tenant context required). Also included in PUBLIC_PATH_PREFIXES above with /v1.0 prefix.
TENANT_PUBLIC_PATH_PREFIXES: tuple[str, ...] = ("/tenants/check", "/m8flow/tenant-login-url")

_CONTEXT_TENANT_ID: ContextVar[Optional[str]] = ContextVar("m8flow_tenant_id", default=None)

# "Are we inside a request handler?" (works for ASGI/WSGI alike)
_REQUEST_ACTIVE: ContextVar[bool] = ContextVar("m8flow_request_active", default=False)

# Local flag to avoid warning spam outside Flask request context
_CONTEXT_WARNED_DEFAULT: ContextVar[bool] = ContextVar("m8flow_warned_default_tenant", default=False)


def allow_missing_tenant_context() -> bool:
    value = os.getenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def begin_request_context() -> Token:
    """Mark the current execution context as handling an HTTP request."""
    return _REQUEST_ACTIVE.set(True)


def end_request_context(token: Token) -> None:
    """Undo begin_request_context()."""
    _REQUEST_ACTIVE.reset(token)


def is_request_active() -> bool:
    return _REQUEST_ACTIVE.get()


def set_context_tenant_id(tenant_id: str | None) -> Token:
    return _CONTEXT_TENANT_ID.set(tenant_id)


def reset_context_tenant_id(token: Token) -> None:
    _CONTEXT_TENANT_ID.reset(token)


def get_context_tenant_id() -> str | None:
    return _CONTEXT_TENANT_ID.get()


def clear_tenant_context() -> None:
    """Clear tenant context variables to prevent cross-request leakage."""
    _CONTEXT_TENANT_ID.set(None)
    _CONTEXT_WARNED_DEFAULT.set(False)


def is_public_request() -> bool:
    return has_request_context() and bool(getattr(g, "_m8flow_public_request", False))


def _warn_default_once(message: str, **extra: object) -> None:
    """
    Warn once per Flask request (via g flag), otherwise once per execution context (ContextVar flag).
    """
    if has_request_context():
        if getattr(g, "_m8flow_warned_default_tenant", False):
            return
        g._m8flow_warned_default_tenant = True
        LOGGER.warning(message, DEFAULT_TENANT_ID, extra=extra)  # type: ignore[arg-type]
        return

    if _CONTEXT_WARNED_DEFAULT.get():
        return
    _CONTEXT_WARNED_DEFAULT.set(True)
    LOGGER.warning(message, extra=extra)  # type: ignore[arg-type]


def get_tenant_id(*, warn_on_default: bool = True) -> str:
    """
    Return the tenant id for the current execution.
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

        if allow_missing_tenant_context():
            g.m8flow_tenant_id = DEFAULT_TENANT_ID
            _CONTEXT_TENANT_ID.set(DEFAULT_TENANT_ID)
            if warn_on_default:
                _warn_default_once(
                    "No tenant id found in request context; defaulting to '%s'.",
                    m8flow_tenant=DEFAULT_TENANT_ID,
                )
            return DEFAULT_TENANT_ID

        raise RuntimeError("Missing tenant id in request context.")

    # Non-request context
    ctx_tid = get_context_tenant_id()
    if ctx_tid:
        return ctx_tid

    if allow_missing_tenant_context():
        _CONTEXT_TENANT_ID.set(DEFAULT_TENANT_ID)
        if warn_on_default:
            _warn_default_once(
                "No tenant id found in non-request context; defaulting to '%s'.",
                m8flow_tenant=DEFAULT_TENANT_ID,
            )
        return DEFAULT_TENANT_ID

    raise RuntimeError("Missing tenant id in non-request context.")


def ensure_tenant_exists(tenant_id: str | None) -> None:
    """Validate that the tenant row exists; raise if missing to enforce pre-provisioning."""
    if not tenant_id:
        raise RuntimeError(
            "Missing tenant id. Ensure the token contains m8flow_tenant_id (or set tenant in request context)."
        )

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from spiffworkflow_backend.models.db import db

    tenant = db.session.get(M8flowTenantModel, tenant_id)

    if tenant is None:
        raise RuntimeError(
            f"Tenant '{tenant_id}' does not exist. Create it in m8flow_tenant before using M8Flow."
        )


def create_tenant_if_not_exists(
    tenant_id: str,
    name: str | None = None,
    slug: str | None = None,
) -> None:
    """Create a tenant row if it does not exist (e.g. after creating a Keycloak realm).
    When slug is provided (e.g. realm name), it is used for M8flowTenantModel.slug;
    otherwise slug defaults to tenant_id (backward compatible).
    """
    if not tenant_id or not tenant_id.strip():
        return
    tenant_id = tenant_id.strip()
    display_name = (name or tenant_id).strip()
    slug_value = (slug or tenant_id).strip()

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from spiffworkflow_backend.models.db import db

    if db.session.get(M8flowTenantModel, tenant_id) is not None:
        return
    # slug, created_by, modified_by are NOT NULL; use slug_value for slug, 'system' for audit when no user context
    tenant = M8flowTenantModel(
        id=tenant_id,
        name=display_name,
        slug=slug_value,
        created_by="system",
        modified_by="system",
    )
    db.session.add(tenant)
    db.session.commit()
    LOGGER.info("Created tenant row for tenant_id=%s name=%s slug=%s", tenant_id, display_name, slug_value)
