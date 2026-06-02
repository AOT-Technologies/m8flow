# m8flow-backend/src/m8flow_backend/routes/process_groups_controller_patch.py
"""Wrap the upstream ``process_group_list`` endpoint so super-admins can filter
the cross-tenant view by ``?tenantId=<id>`` and so every response item carries
``tenantId`` and ``tenantName`` for the UI.

The cross-tenant iteration itself happens in
``process_model_service_patch.patched_get_process_groups_for_api`` — this
controller patch only:

1. Pulls the optional ``tenantId``/``tenant_id`` query param and stashes it on
   flask.g so the service patch can short-circuit to the matching tenant only.
2. After the upstream controller serializes the response (which drops dynamic
   attributes because ``ProcessGroup.serialized()`` uses ``dataclasses.asdict``),
   walks the tenant map the service patch built on flask.g and re-injects
   ``tenantId`` / ``tenantName`` per item.
"""
from __future__ import annotations

import importlib
from typing import Any, Callable

import flask.wrappers
from flask import g
from flask import jsonify
from flask import make_response
from flask import request as flask_request

_PATCHED = False
_ORIGINAL_PROCESS_GROUP_LIST: Callable[..., Any] | None = None
_ORIGINAL_PROCESS_GROUP_SHOW: Callable[..., Any] | None = None


def _resolve_tenant_filter_from_request() -> str | None:
    value = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _tenant_name_map(tenant_ids: set[str]) -> dict[str, str]:
    if not tenant_ids:
        return {}
    # Lazy import to avoid SQLAlchemy metadata conflicts at module load time
    # when unrelated test fixtures reload the upstream model modules.
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

    tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
    return {t.id: t.name for t in tenants}


def _enrich_results_with_tenant_info(response: flask.wrappers.Response) -> flask.wrappers.Response:
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict):
        return response

    results = payload.get("results")
    if not isinstance(results, list):
        return response

    group_tenant_map: dict[str, str] = getattr(g, "_m8flow_process_group_tenant_map", {}) or {}
    if not group_tenant_map:
        return response

    tenant_name_by_id = _tenant_name_map(set(group_tenant_map.values()))

    for item in results:
        if not isinstance(item, dict):
            continue
        group_id = item.get("id")
        if not isinstance(group_id, str):
            continue
        tenant_id = group_tenant_map.get(group_id)
        if tenant_id is None:
            continue
        item["tenantId"] = tenant_id
        item["tenantName"] = tenant_name_by_id.get(tenant_id)

    return make_response(jsonify(payload), response.status_code)


def _enrich_single_process_group_response(
    response: flask.wrappers.Response,
) -> flask.wrappers.Response:
    """Inject tenantId / tenantName into a single-group show response.

    The patched ``ProcessModelService.get_process_group`` calls
    ``_lock_super_admin_tenant_for_process_group`` which sets
    ``g.m8flow_tenant_id``; we read that here.
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
    global _PATCHED, _ORIGINAL_PROCESS_GROUP_LIST, _ORIGINAL_PROCESS_GROUP_SHOW
    if not _PATCHED:
        return
    mod = importlib.import_module("spiffworkflow_backend.routes.process_groups_controller")
    if _ORIGINAL_PROCESS_GROUP_LIST is not None:
        mod.process_group_list = _ORIGINAL_PROCESS_GROUP_LIST
        _ORIGINAL_PROCESS_GROUP_LIST = None
    if _ORIGINAL_PROCESS_GROUP_SHOW is not None:
        mod.process_group_show = _ORIGINAL_PROCESS_GROUP_SHOW
        _ORIGINAL_PROCESS_GROUP_SHOW = None
    _PATCHED = False


def apply() -> None:
    global _PATCHED, _ORIGINAL_PROCESS_GROUP_LIST, _ORIGINAL_PROCESS_GROUP_SHOW
    if _PATCHED:
        return

    mod = importlib.import_module("spiffworkflow_backend.routes.process_groups_controller")
    upstream_list = mod.process_group_list
    upstream_show = mod.process_group_show
    _ORIGINAL_PROCESS_GROUP_LIST = upstream_list
    _ORIGINAL_PROCESS_GROUP_SHOW = upstream_show

    def _patched_process_group_list(
        process_group_identifier: str | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> flask.wrappers.Response:
        tenant_filter = _resolve_tenant_filter_from_request()
        previous_filter = getattr(g, "_m8flow_process_tenant_filter", None)
        previous_map = getattr(g, "_m8flow_process_group_tenant_map", None)
        if tenant_filter:
            g._m8flow_process_tenant_filter = tenant_filter
        g._m8flow_process_group_tenant_map = {}
        try:
            response = upstream_list(
                process_group_identifier=process_group_identifier,
                page=page,
                per_page=per_page,
            )
        finally:
            if previous_filter is None:
                if hasattr(g, "_m8flow_process_tenant_filter"):
                    delattr(g, "_m8flow_process_tenant_filter")
            else:
                g._m8flow_process_tenant_filter = previous_filter

        enriched = _enrich_results_with_tenant_info(response)

        if previous_map is None:
            if hasattr(g, "_m8flow_process_group_tenant_map"):
                delattr(g, "_m8flow_process_group_tenant_map")
        else:
            g._m8flow_process_group_tenant_map = previous_map

        return enriched

    def _patched_process_group_show(modified_process_group_id: str) -> flask.wrappers.Response:
        response = upstream_show(modified_process_group_id)
        return _enrich_single_process_group_response(response)

    mod.process_group_list = _patched_process_group_list
    mod.process_group_show = _patched_process_group_show
    _PATCHED = True
