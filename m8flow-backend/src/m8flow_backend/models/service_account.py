"""m8flow compatibility shim for spiffworkflow_backend.models.service_account.

The model is defined upstream by SpiffArena (LGPL-2.1). m8flow's schema delta -
the m8f_tenant_id column and any constraint changes - is applied centrally by
m8flow_backend.models.tenant_schema. This module contributes nothing of its own.

Kept so that existing `from m8flow_backend.models.service_account import ...` imports keep
working. New code should import from spiffworkflow_backend.models.service_account directly.

DO NOT reintroduce model definitions here. Schema changes belong in
m8flow_backend/models/tenant_schema.py.
"""
from __future__ import annotations

from spiffworkflow_backend.models.service_account import (  # noqa: F401
    SPIFF_SERVICE_ACCOUNT_AUTH_SERVICE,
    SPIFF_SERVICE_ACCOUNT_AUTH_SERVICE_ID_PREFIX,
    ServiceAccountModel,
)

__all__ = [
    "SPIFF_SERVICE_ACCOUNT_AUTH_SERVICE",
    "SPIFF_SERVICE_ACCOUNT_AUTH_SERVICE_ID_PREFIX",
    "ServiceAccountModel",
]
