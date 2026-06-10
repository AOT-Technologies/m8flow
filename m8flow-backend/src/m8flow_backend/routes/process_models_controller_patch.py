# m8flow-backend/src/m8flow_backend/routes/process_models_controller_patch.py
from __future__ import annotations

import importlib
from typing import Any, Callable

import flask.wrappers
from flask import g
from flask import jsonify
from flask import make_response
from flask import request as flask_request

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.tenancy import is_super_admin_request
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db  # noqa: F401

_PATCHED = False
_ORIGINAL_PROCESS_MODEL_CREATE: Callable[..., Any] | None = None
_ORIGINAL_PROCESS_MODEL_LIST: Callable[..., Any] | None = None
_ORIGINAL_PROCESS_MODEL_SHOW: Callable[..., Any] | None = None


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


def _resolve_tenant_filter_from_request() -> str | None:
    value = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _tenant_name_map(tenant_ids: set[str]) -> dict[str, str]:
    if not tenant_ids:
        return {}
    tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()  # type: ignore[attr-defined]
    return {tenant.id: tenant.name for tenant in tenants}


def _walk_results_and_inject_tenant(
    results: Any,
    model_tenant_map: dict[str, str],
    group_tenant_map: dict[str, str],
    tenant_name_by_id: dict[str, str],
) -> None:
    """Walk a possibly-nested ``results`` payload and inject tenantId / tenantName.

    ``process_model_list`` returns either a flat list of process-model dicts or
    (when ``group_by_process_group`` is true) a list of group dicts each
    containing a nested ``process_models`` list. We walk both shapes.
    """
    if not isinstance(results, list):
        return
    for item in results:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str):
            model_tenant_id = model_tenant_map.get(item_id)
            group_tenant_id = group_tenant_map.get(item_id)
            tenant_id = model_tenant_id or group_tenant_id
            if tenant_id is not None:
                item["tenantId"] = tenant_id
                item["tenantName"] = tenant_name_by_id.get(tenant_id)
        nested = item.get("process_models")
        if isinstance(nested, list):
            _walk_results_and_inject_tenant(
                nested, model_tenant_map, group_tenant_map, tenant_name_by_id
            )


def _enrich_process_model_list_response(response: flask.wrappers.Response) -> flask.wrappers.Response:
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict):
        return response
    results = payload.get("results")
    if not isinstance(results, list):
        return response

    model_tenant_map: dict[str, str] = getattr(g, "_m8flow_process_model_tenant_map", {}) or {}
    group_tenant_map: dict[str, str] = getattr(g, "_m8flow_process_group_tenant_map", {}) or {}
    if not model_tenant_map and not group_tenant_map:
        return response

    tenant_ids = set(model_tenant_map.values()) | set(group_tenant_map.values())
    tenant_name_by_id = _tenant_name_map(tenant_ids)

    _walk_results_and_inject_tenant(results, model_tenant_map, group_tenant_map, tenant_name_by_id)
    return make_response(jsonify(payload), response.status_code)


def _enrich_single_process_model_response(
    response: flask.wrappers.Response,
) -> flask.wrappers.Response:
    """Inject tenantId / tenantName into a single-model show response.

    The upstream show endpoint locks the owning tenant via
    ``patched_get_process_model`` (which calls
    ``_lock_super_admin_tenant_for_process_model``), so the tenant id is
    available on ``g.m8flow_tenant_id``.
    """
    tenant_id = getattr(g, "m8flow_tenant_id", None)
    if not isinstance(tenant_id, str) or not tenant_id:
        return response
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict):
        return response
    tenant_name_by_id = _tenant_name_map({tenant_id})
    payload["tenantId"] = tenant_id
    payload["tenantName"] = tenant_name_by_id.get(tenant_id)
    return make_response(jsonify(payload), response.status_code)


def reset() -> None:
    """Restore upstream controller (for tests)."""
    global _PATCHED, _ORIGINAL_PROCESS_MODEL_CREATE, _ORIGINAL_PROCESS_MODEL_LIST, _ORIGINAL_PROCESS_MODEL_SHOW
    if not _PATCHED:
        return
    mod = importlib.import_module("spiffworkflow_backend.routes.process_models_controller")
    if _ORIGINAL_PROCESS_MODEL_CREATE is not None:
        mod.process_model_create = _ORIGINAL_PROCESS_MODEL_CREATE
        _ORIGINAL_PROCESS_MODEL_CREATE = None
    if _ORIGINAL_PROCESS_MODEL_LIST is not None:
        mod.process_model_list = _ORIGINAL_PROCESS_MODEL_LIST
        _ORIGINAL_PROCESS_MODEL_LIST = None
    if _ORIGINAL_PROCESS_MODEL_SHOW is not None:
        mod.process_model_show = _ORIGINAL_PROCESS_MODEL_SHOW
        _ORIGINAL_PROCESS_MODEL_SHOW = None
    _PATCHED = False


def apply() -> None:
    """Wrap process_model_create (m8f_tenant_id stripping), process_model_list (tenant filter + enrich),
    and process_model_show (tenant chip enrichment)."""
    global _PATCHED, _ORIGINAL_PROCESS_MODEL_CREATE, _ORIGINAL_PROCESS_MODEL_LIST, _ORIGINAL_PROCESS_MODEL_SHOW
    if _PATCHED:
        return

    mod = importlib.import_module("spiffworkflow_backend.routes.process_models_controller")
    upstream_create = mod.process_model_create
    upstream_list = mod.process_model_list
    upstream_show = mod.process_model_show
    _ORIGINAL_PROCESS_MODEL_CREATE = upstream_create
    _ORIGINAL_PROCESS_MODEL_LIST = upstream_list
    _ORIGINAL_PROCESS_MODEL_SHOW = upstream_show

    def _patched_process_model_create(
        modified_process_group_id: str,
        body: dict[str, str | bool | int | None | list],
    ) -> Any:
        body_for_upstream = prepare_process_model_create_body_for_upstream(body)
        return upstream_create(modified_process_group_id, body_for_upstream)

    def _patched_process_model_list(
        process_group_identifier: str | None = None,
        recursive: bool | None = False,
        filter_runnable_by_user: bool | None = False,
        include_parent_groups: bool | None = False,
        group_by_process_group: bool | None = False,
        page: int = 1,
        per_page: int = 100,
    ) -> flask.wrappers.Response:
        tenant_filter = _resolve_tenant_filter_from_request()
        previous_filter = getattr(g, "_m8flow_process_tenant_filter", None)
        previous_model_map = getattr(g, "_m8flow_process_model_tenant_map", None)
        previous_group_map = getattr(g, "_m8flow_process_group_tenant_map", None)
        if tenant_filter:
            g._m8flow_process_tenant_filter = tenant_filter
        g._m8flow_process_model_tenant_map = {}
        g._m8flow_process_group_tenant_map = {}
        try:
            response = upstream_list(
                process_group_identifier=process_group_identifier,
                recursive=recursive,
                filter_runnable_by_user=filter_runnable_by_user,
                include_parent_groups=include_parent_groups,
                group_by_process_group=group_by_process_group,
                page=page,
                per_page=per_page,
            )
        finally:
            if previous_filter is None:
                if hasattr(g, "_m8flow_process_tenant_filter"):
                    delattr(g, "_m8flow_process_tenant_filter")
            else:
                g._m8flow_process_tenant_filter = previous_filter

        enriched = _enrich_process_model_list_response(response)

        if previous_model_map is None:
            if hasattr(g, "_m8flow_process_model_tenant_map"):
                delattr(g, "_m8flow_process_model_tenant_map")
        else:
            g._m8flow_process_model_tenant_map = previous_model_map
        if previous_group_map is None:
            if hasattr(g, "_m8flow_process_group_tenant_map"):
                delattr(g, "_m8flow_process_group_tenant_map")
        else:
            g._m8flow_process_group_tenant_map = previous_group_map

        return enriched

    def _patched_process_model_show(
        modified_process_model_identifier: str,
        include_file_references: bool = False,
    ) -> flask.wrappers.Response:
        response = upstream_show(
            modified_process_model_identifier,
            include_file_references=include_file_references,
        )
        return _enrich_single_process_model_response(response)

    mod.process_model_create = _patched_process_model_create
    mod.process_model_list = _patched_process_model_list
    mod.process_model_show = _patched_process_model_show
    _PATCHED = True
