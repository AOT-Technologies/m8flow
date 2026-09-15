"""Pluggable auth-provider seam.

Callers obtain the active provider with ``get_auth_provider()``. A second
implementation registers via ``register_auth_provider`` without touching those
call sites.
"""
from m8flow_backend.integrations.auth.factory import (
    get_auth_provider,
    register_auth_provider,
    reset_auth_provider,
)

__all__ = [
    "get_auth_provider",
    "register_auth_provider",
    "reset_auth_provider",
]
