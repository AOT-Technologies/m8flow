# extensions/m8flow-backend/src/m8flow_backend/tenancy.py
from __future__ import annotations

import logging
import os
from contextvars import ContextVar, Token
from typing import Optional, cast

from flask import g, has_request_context

LOGGER = logging.getLogger(__name__)

DEFAULT_TENANT_ID = os.getenv("M8FLOW_DEFAULT_TENANT_ID", "default")

_CONTEXT_TENANT_ID: ContextVar[Optional[str]] = ContextVar("m8flow_tenant_id", default=None)

# "Are we inside a request handler?" (works for ASGI/WSGI alike)
_REQUEST_ACTIVE: ContextVar[bool] = ContextVar("m8flow_request_active", default=False)

# Local flag to avoid warning spam outside Flask request context
_CONTEXT_WARNED_DEFAULT: ContextVar[bool] = ContextVar("m8flow_warned_default_tenant", default=False)

PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/v1.0/status",
    "/v1.0/openapi.json",
    "/v1.0/openapi.yaml",
    "/v1.0/ui",
    "/v1.0/static",
)


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

