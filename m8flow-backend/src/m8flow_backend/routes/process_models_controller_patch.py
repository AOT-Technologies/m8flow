# m8flow-backend/src/m8flow_backend/routes/process_models_controller_patch.py
from __future__ import annotations

import importlib
from typing import Any, Callable

from m8flow_backend.tenancy import is_super_admin_request
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db  # noqa: F401

_PATCHED = False
_ORIGINAL_PROCESS_MODEL_CREATE: Callable[..., Any] | None = None


def prepare_process_model_create_body_for_upstream(
    body: dict[str, str | bool | int | None | list],
) -> dict[str, str | bool | int | None | list]:
    """Copy body for upstream handler; strips ``m8f_tenant_id`` from the payload.

    Super-admin is read-only across tenants and cannot create process models.
    """
    body_for_upstream = dict(body)
    raw_tid = body_for_upstream.pop("m8f_tenant_id", None)
    if is_super_admin_request():
        raise ApiError(
            error_code="forbidden",
            message="Super-admin is read-only across tenants.",
            status_code=403,
        )
    # Non-super-admin calls may still include m8f_tenant_id from older clients;
    # ignore it and rely on normal tenant scoping instead.
    _ = raw_tid

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
