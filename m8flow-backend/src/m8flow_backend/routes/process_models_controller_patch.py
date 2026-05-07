# m8flow-backend/src/m8flow_backend/routes/process_models_controller_patch.py
from __future__ import annotations

import importlib
from typing import Any, Callable

from flask import g

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.tenancy import is_super_admin_request, set_context_tenant_id
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db

_PATCHED = False
_ORIGINAL_PROCESS_MODEL_CREATE: Callable[..., Any] | None = None


def prepare_process_model_create_body_for_upstream(
    body: dict[str, str | bool | int | None | list],
) -> dict[str, str | bool | int | None | list]:
    """Copy body for upstream handler; super-admin may lock tenant from ``m8f_tenant_id`` (stripped from copy)."""
    body_for_upstream = dict(body)
    raw_tid = body_for_upstream.pop("m8f_tenant_id", None)
    if is_super_admin_request() and raw_tid is not None:
        tenant_id = str(raw_tid).strip()
        if not tenant_id:
            raise ApiError(
                error_code="invalid_tenant_id",
                message="m8f_tenant_id must be a non-empty string when provided.",
                status_code=400,
            )
        tenant = db.session.get(M8flowTenantModel, tenant_id)
        if tenant is None:
            raise ApiError(
                error_code="tenant_not_found",
                message=f"Tenant not found: {tenant_id}",
                status_code=400,
            )
        g.m8flow_tenant_id = tenant_id
        set_context_tenant_id(tenant_id)

    return body_for_upstream


def reset() -> None:
    """Restore upstream controller (for tests)."""
    global _PATCHED, _ORIGINAL_PROCESS_MODEL_CREATE
    if not _PATCHED or _ORIGINAL_PROCESS_MODEL_CREATE is None:
        return
    mod = importlib.import_module("spiffworkflow_backend.routes.process_models_controller")
    mod.process_model_create = _ORIGINAL_PROCESS_MODEL_CREATE
    _ORIGINAL_PROCESS_MODEL_CREATE = None
    _PATCHED = False


def apply() -> None:
    """Wrap process_model_create so super-admin can lock tenant via body m8f_tenant_id."""
    global _PATCHED, _ORIGINAL_PROCESS_MODEL_CREATE
    if _PATCHED:
        return

    mod = importlib.import_module("spiffworkflow_backend.routes.process_models_controller")
    upstream_create = mod.process_model_create
    _ORIGINAL_PROCESS_MODEL_CREATE = upstream_create

    def _patched_process_model_create(
        modified_process_group_id: str,
        body: dict[str, str | bool | int | None | list],
    ) -> Any:
        body_for_upstream = prepare_process_model_create_body_for_upstream(body)
        return upstream_create(modified_process_group_id, body_for_upstream)

    mod.process_model_create = _patched_process_model_create
    _PATCHED = True
