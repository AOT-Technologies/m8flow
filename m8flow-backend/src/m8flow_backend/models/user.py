"""m8flow compatibility shim for spiffworkflow_backend.models.user.

The model is defined upstream by SpiffArena (LGPL-2.1). m8flow's schema delta -
the m8f_tenant_id column and any constraint changes - is applied centrally by
m8flow_backend.models.tenant_schema. This module contributes nothing of its own.

Kept so that existing `from m8flow_backend.models.user import ...` imports keep
working. New code should import from spiffworkflow_backend.models.user directly.

DO NOT reintroduce model definitions here. Schema changes belong in
m8flow_backend/models/tenant_schema.py.
"""
from __future__ import annotations

from spiffworkflow_backend.models.user import (  # noqa: F401
    SPIFF_NO_AUTH_USER,
    SPIFF_GUEST_USER,
    SPIFF_SYSTEM_USER,
    SPIFF_GENERATED_JWT_KEY_ID,
    SPIFF_GENERATED_JWT_ALGORITHM,
    SPIFF_GENERATED_JWT_AUDIENCE,
    UserNotFoundError,
    UserModel,
)

__all__ = [
    "SPIFF_NO_AUTH_USER",
    "SPIFF_GUEST_USER",
    "SPIFF_SYSTEM_USER",
    "SPIFF_GENERATED_JWT_KEY_ID",
    "SPIFF_GENERATED_JWT_ALGORITHM",
    "SPIFF_GENERATED_JWT_AUDIENCE",
    "UserNotFoundError",
    "UserModel",
]
