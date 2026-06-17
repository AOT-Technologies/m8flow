"""Context management utilities for storing request-scoped data."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

# Context variables for storing request-scoped data
AUTH_TOKEN_KEY = "auth_token"
TENANT_ID_KEY = "tenant_id"
COMPANY_ID_KEY = "company_id"  # For compatibility

_auth_token_var: ContextVar[str | None] = ContextVar(AUTH_TOKEN_KEY, default=None)
_tenant_id_var: ContextVar[str | None] = ContextVar(TENANT_ID_KEY, default=None)
_company_id_var: ContextVar[str | None] = ContextVar(COMPANY_ID_KEY, default=None)


def get_auth_token() -> str | None:
    """Get authentication token from context.

    Returns:
        Authentication token or None if not set.
    """
    return _auth_token_var.get()


def set_auth_token(token: str) -> None:
    """Set authentication token in context.

    Args:
        token: Authentication token to set.
    """
    _auth_token_var.set(token)


def get_tenant_id() -> str | None:
    """Get tenant ID from context.

    Returns:
        Tenant ID or None if not set.
    """
    return _tenant_id_var.get()


def set_tenant_id(tenant_id: str) -> None:
    """Set tenant ID in context.

    Args:
        tenant_id: Tenant ID to set.
    """
    _tenant_id_var.set(tenant_id)


def get_company_id_safe() -> str | None:
    """Get company ID from context (alias for tenant_id for compatibility).

    Returns:
        Company/Tenant ID or None if not set.
    """
    return _company_id_var.get() or get_tenant_id()


def set_company_id(company_id: str) -> None:
    """Set company ID in context.

    Args:
        company_id: Company ID to set.
    """
    _company_id_var.set(company_id)


def clear_context() -> None:
    """Clear all context variables."""
    _auth_token_var.set(None)
    _tenant_id_var.set(None)
    _company_id_var.set(None)
