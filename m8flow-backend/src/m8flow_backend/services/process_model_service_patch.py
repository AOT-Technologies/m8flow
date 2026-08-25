from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from flask import g, has_request_context

from m8flow_backend.tenancy import reset_context_tenant_id, set_context_tenant_id
from m8flow_backend.tenancy import is_super_admin_request

_PATCHED = False
_ORIGINAL_METHODS: dict[str, Any] = {}
SUPER_ADMIN_READ_ONLY_MESSAGE = "Super-admin is read-only across tenants."


def reset() -> None:
    """Restore ProcessModelService classmethods (for tests). Safe no-op if not patched."""
    global _PATCHED
    if not _PATCHED:
        return
    from spiffworkflow_backend.services.process_model_service import ProcessModelService

    for name, descriptor in _ORIGINAL_METHODS.items():
        setattr(ProcessModelService, name, descriptor)
    _ORIGINAL_METHODS.clear()
    _PATCHED = False


def _tenant_roots(base_dir: str) -> list[str]:
    if not os.path.isdir(base_dir):
        return []
    roots: list[str] = []
    with os.scandir(base_dir) as entries:
        for entry in entries:
            if not entry.is_dir():
                continue
            name = entry.name.strip()
            if not name or name.startswith('.'):
                continue
            roots.append(name)
    roots.sort()
    return roots


def _live_tenant_root_bindings(base_dir: str) -> list[tuple[str, str]]:
    """Return live-tenant bindings as ``(canonical_tenant_id, filesystem_root)``."""
    if not os.path.isdir(base_dir):
        return []

    try:
        from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
        from spiffworkflow_backend.models.db import db

        tenants = (
            db.session.query(M8flowTenantModel)
            .order_by(M8flowTenantModel.slug.asc(), M8flowTenantModel.id.asc())
            .all()
        )
    except Exception:
        return []

    bindings: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for tenant in tenants:
        tenant_id = getattr(tenant, "id", None)
        if not isinstance(tenant_id, str):
            continue
        normalized_tenant_id = tenant_id.strip()
        if not normalized_tenant_id:
            continue

        # BPMN roots are enforced to use the canonical tenant id only. Slug-
        # named directories are intentionally ignored so every lookup path is
        # anchored to the same tenant key the database and request context use.
        candidate_path = os.path.join(base_dir, normalized_tenant_id)
        if not os.path.isdir(candidate_path):
            continue
        binding = (normalized_tenant_id, normalized_tenant_id)
        if binding in seen:
            continue
        seen.add(binding)
        bindings.append(binding)

    return bindings


def _tenant_filter_matches(binding: tuple[str, str], tenant_id_filter: str | None) -> bool:
    if not isinstance(tenant_id_filter, str):
        return True

    normalized_filter = tenant_id_filter.strip()
    if not normalized_filter:
        return True

    binding_tenant_id, binding_root = binding
    if normalized_filter in {binding_tenant_id, binding_root}:
        return True

    try:
        from m8flow_backend.services.tenant_identity_helpers import _canonical_tenant_id_from_identifiers

        canonical_filter = _canonical_tenant_id_from_identifiers(normalized_filter)
    except Exception:
        canonical_filter = None

    return canonical_filter == binding_tenant_id


def _lock_super_admin_tenant_for_process_model(base_dir: str, process_model_id: str) -> None:
    """If super-admin has no tenant set, find owning tenant on disk and lock g + ContextVar."""
    if not is_super_admin_request() or not has_request_context():
        return
    if getattr(g, "m8flow_tenant_id", None):
        return
    if not base_dir or not os.path.isdir(base_dir):
        return

    from spiffworkflow_backend.services.file_system_service import FileSystemService

    rel = process_model_id.replace("/", os.sep)
    for tenant_id, tenant_root in _live_tenant_root_bindings(base_dir):
        candidate = os.path.join(base_dir, tenant_root, rel, FileSystemService.PROCESS_MODEL_JSON_FILE)
        if os.path.isfile(candidate):
            g.m8flow_tenant_id = tenant_id
            g._m8flow_bpmn_root_tenant = tenant_root
            set_context_tenant_id(tenant_id)
            return


def _lock_super_admin_tenant_for_process_group(base_dir: str, process_group_id: str) -> None:
    """If super-admin has no tenant set, find owning tenant on disk and lock g + ContextVar."""
    if not is_super_admin_request() or not has_request_context():
        return
    if getattr(g, "m8flow_tenant_id", None):
        return
    if not base_dir or not os.path.isdir(base_dir):
        return

    from spiffworkflow_backend.services.file_system_service import FileSystemService

    rel = process_group_id.replace("/", os.sep)
    for tenant_id, tenant_root in _live_tenant_root_bindings(base_dir):
        candidate = os.path.join(base_dir, tenant_root, rel, FileSystemService.PROCESS_GROUP_JSON_FILE)
        if os.path.isfile(candidate):
            g.m8flow_tenant_id = tenant_id
            g._m8flow_bpmn_root_tenant = tenant_root
            set_context_tenant_id(tenant_id)
            return


@contextmanager
def _temporary_tenant_context(tenant_id: str, tenant_root: str | None = None):
    prev_request_tenant = getattr(g, "m8flow_tenant_id", None) if has_request_context() else None
    prev_bpmn_root_tenant = getattr(g, "_m8flow_bpmn_root_tenant", None) if has_request_context() else None
    token = set_context_tenant_id(tenant_id)
    try:
        if has_request_context():
            g.m8flow_tenant_id = tenant_id
            if tenant_root:
                g._m8flow_bpmn_root_tenant = tenant_root
            elif hasattr(g, "_m8flow_bpmn_root_tenant"):
                delattr(g, "_m8flow_bpmn_root_tenant")
        yield
    finally:
        reset_context_tenant_id(token)
        if has_request_context():
            if prev_request_tenant is None:
                if hasattr(g, "m8flow_tenant_id"):
                    delattr(g, "m8flow_tenant_id")
            else:
                g.m8flow_tenant_id = prev_request_tenant
            if prev_bpmn_root_tenant is None:
                if hasattr(g, "_m8flow_bpmn_root_tenant"):
                    delattr(g, "_m8flow_bpmn_root_tenant")
            else:
                g._m8flow_bpmn_root_tenant = prev_bpmn_root_tenant


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from flask import current_app
    from spiffworkflow_backend.exceptions.api_error import ApiError
    from spiffworkflow_backend.services.process_model_service import ProcessModelService

    _ORIGINAL_METHODS["get_process_groups_for_api"] = ProcessModelService.get_process_groups_for_api
    _ORIGINAL_METHODS["get_process_models_for_api"] = ProcessModelService.get_process_models_for_api
    _ORIGINAL_METHODS["get_process_model"] = ProcessModelService.get_process_model
    _ORIGINAL_METHODS["is_process_model_identifier"] = ProcessModelService.is_process_model_identifier
    _ORIGINAL_METHODS["is_process_group_identifier"] = ProcessModelService.is_process_group_identifier
    _ORIGINAL_METHODS["get_process_group"] = ProcessModelService.get_process_group
    _ORIGINAL_METHODS["save_process_model"] = ProcessModelService.save_process_model
    _ORIGINAL_METHODS["process_model_delete"] = ProcessModelService.process_model_delete
    _ORIGINAL_METHODS["process_model_move"] = ProcessModelService.process_model_move
    _ORIGINAL_METHODS["copy_process_model"] = ProcessModelService.copy_process_model
    _ORIGINAL_METHODS["add_process_group"] = ProcessModelService.add_process_group
    _ORIGINAL_METHODS["update_process_group"] = ProcessModelService.update_process_group
    _ORIGINAL_METHODS["process_group_move"] = ProcessModelService.process_group_move
    _ORIGINAL_METHODS["process_group_delete"] = ProcessModelService.process_group_delete

    original_get_process_groups_for_api = ProcessModelService.get_process_groups_for_api.__func__
    original_get_process_models_for_api = ProcessModelService.get_process_models_for_api.__func__
    original_get_process_model = ProcessModelService.get_process_model.__func__
    original_is_process_model_identifier = ProcessModelService.is_process_model_identifier.__func__
    original_is_process_group_identifier = ProcessModelService.is_process_group_identifier.__func__
    original_get_process_group = ProcessModelService.get_process_group.__func__
    original_save_process_model = ProcessModelService.save_process_model.__func__
    original_process_model_delete = ProcessModelService.process_model_delete.__func__
    original_process_model_move = ProcessModelService.process_model_move.__func__
    original_copy_process_model = ProcessModelService.copy_process_model.__func__
    original_add_process_group = ProcessModelService.add_process_group.__func__
    original_update_process_group = ProcessModelService.update_process_group.__func__
    original_process_group_move = ProcessModelService.process_group_move.__func__
    original_process_group_delete = ProcessModelService.process_group_delete.__func__

    def _resolve_tenant_filter(tenant_id_filter: str | None) -> str | None:
        if tenant_id_filter:
            return tenant_id_filter
        if has_request_context():
            request_filter = getattr(g, "_m8flow_process_tenant_filter", None)
            if isinstance(request_filter, str) and request_filter:
                return request_filter
        return None

    def _record_tenant_for_item(map_key: str, item_id: str, tenant_id: str) -> None:
        """Record an item_id -> tenant_id mapping on flask.g for controller-layer enrichment.

        The dataclass-based ``ProcessGroup.serialized()`` and the default
        json serializer for ``ProcessModelInfo`` drop attributes set via
        ``setattr``, so the controller patch needs an out-of-band mapping
        to re-attach ``tenantId``/``tenantName`` to each response item.
        """
        if not has_request_context():
            return
        existing = getattr(g, map_key, None)
        if not isinstance(existing, dict):
            existing = {}
            setattr(g, map_key, existing)
        existing[item_id] = tenant_id

    def _record_process_group_tree_tenant(group: Any, tenant_id: str) -> None:
        """Record tenant ownership for a process-group tree and its nested models."""
        group_id = getattr(group, "id", None)
        if isinstance(group_id, str):
            _record_tenant_for_item("_m8flow_process_group_tenant_map", group_id, tenant_id)
        if not getattr(group, "tenant_id", None):
            setattr(group, "tenant_id", tenant_id)

        process_models = getattr(group, "process_models", None)
        if isinstance(process_models, list):
            for process_model in process_models:
                process_model_id = getattr(process_model, "id", None)
                if isinstance(process_model_id, str):
                    _record_tenant_for_item(
                        "_m8flow_process_model_tenant_map",
                        process_model_id,
                        tenant_id,
                    )
                if not getattr(process_model, "tenant_id", None):
                    setattr(process_model, "tenant_id", tenant_id)

        process_groups = getattr(group, "process_groups", None)
        if isinstance(process_groups, list):
            for nested_group in process_groups:
                _record_process_group_tree_tenant(nested_group, tenant_id)

    @classmethod
    def patched_get_process_groups_for_api(
        cls,
        process_group_id: str | None = None,
        user: Any | None = None,
        tenant_id_filter: str | None = None,
    ):
        if not is_super_admin_request():
            groups = original_get_process_groups_for_api(cls, process_group_id=process_group_id, user=user)
            current_tenant_id: str | None = (
                getattr(g, "m8flow_tenant_id", None) if has_request_context() else None
            )
            if current_tenant_id:
                for group in groups:
                    _record_process_group_tree_tenant(group, current_tenant_id)
            return groups

        base_dir = current_app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"]
        tenant_bindings = _live_tenant_root_bindings(base_dir)
        effective_filter = _resolve_tenant_filter(tenant_id_filter)
        if effective_filter:
            tenant_bindings = [binding for binding in tenant_bindings if _tenant_filter_matches(binding, effective_filter)]

        merged: list[Any] = []
        seen: set[str] = set()

        for tenant_id, tenant_root in tenant_bindings:
            with _temporary_tenant_context(tenant_id, tenant_root):
                groups = original_get_process_groups_for_api(cls, process_group_id=process_group_id, user=user)
                for group in groups:
                    group_id = getattr(group, "id", None)
                    if isinstance(group_id, str) and group_id in seen:
                        continue
                    if isinstance(group_id, str):
                        seen.add(group_id)
                    _record_process_group_tree_tenant(group, tenant_id)
                    merged.append(group)

        return merged

    @classmethod
    def patched_get_process_models_for_api(
        cls,
        user: Any,
        process_group_id: str | None = None,
        recursive: bool | None = False,
        filter_runnable_by_user: bool | None = False,
        filter_runnable_as_extension: bool | None = False,
        include_files: bool | None = False,
        tenant_id_filter: str | None = None,
    ):
        if not is_super_admin_request():
            process_models = original_get_process_models_for_api(
                cls,
                user=user,
                process_group_id=process_group_id,
                recursive=recursive,
                filter_runnable_by_user=filter_runnable_by_user,
                filter_runnable_as_extension=filter_runnable_as_extension,
                include_files=include_files,
            )
            current_tenant_id: str | None = (
                getattr(g, "m8flow_tenant_id", None) if has_request_context() else None
            )
            if current_tenant_id:
                for process_model in process_models:
                    if not getattr(process_model, "tenant_id", None):
                        setattr(process_model, "tenant_id", current_tenant_id)
                    pmid = getattr(process_model, "id", None)
                    if isinstance(pmid, str):
                        _record_tenant_for_item("_m8flow_process_model_tenant_map", pmid, current_tenant_id)
            return process_models

        base_dir = current_app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"]
        tenant_bindings = _live_tenant_root_bindings(base_dir)
        effective_filter = _resolve_tenant_filter(tenant_id_filter)
        if effective_filter:
            tenant_bindings = [binding for binding in tenant_bindings if _tenant_filter_matches(binding, effective_filter)]

        merged: list[Any] = []
        seen: set[str] = set()

        for tenant_id, tenant_root in tenant_bindings:
            with _temporary_tenant_context(tenant_id, tenant_root):
                process_models = original_get_process_models_for_api(
                    cls,
                    user=user,
                    process_group_id=process_group_id,
                    recursive=recursive,
                    filter_runnable_by_user=filter_runnable_by_user,
                    filter_runnable_as_extension=filter_runnable_as_extension,
                    include_files=include_files,
                )
                for process_model in process_models:
                    process_model_id = getattr(process_model, "id", None)
                    if isinstance(process_model_id, str) and process_model_id in seen:
                        continue
                    if isinstance(process_model_id, str):
                        seen.add(process_model_id)
                        _record_tenant_for_item("_m8flow_process_model_tenant_map", process_model_id, tenant_id)
                    setattr(process_model, "tenant_id", tenant_id)
                    merged.append(process_model)

        return merged

    @classmethod
    def patched_get_process_model(cls, process_model_id: str):
        if is_super_admin_request() and has_request_context() and not getattr(g, "m8flow_tenant_id", None):
            base_dir = current_app.config.get("SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR")
            if isinstance(base_dir, str):
                _lock_super_admin_tenant_for_process_model(base_dir, process_model_id)
        return original_get_process_model(cls, process_model_id)

    @classmethod
    def patched_is_process_model_identifier(cls, process_model_identifier: str) -> bool:
        if is_super_admin_request() and has_request_context() and not getattr(g, "m8flow_tenant_id", None):
            base_dir = current_app.config.get("SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR")
            if isinstance(base_dir, str):
                _lock_super_admin_tenant_for_process_model(base_dir, process_model_identifier)
        return original_is_process_model_identifier(cls, process_model_identifier)

    @classmethod
    def patched_is_process_group_identifier(cls, process_group_identifier: str) -> bool:
        if is_super_admin_request() and has_request_context() and not getattr(g, "m8flow_tenant_id", None):
            base_dir = current_app.config.get("SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR")
            if isinstance(base_dir, str):
                _lock_super_admin_tenant_for_process_group(base_dir, process_group_identifier)
        return original_is_process_group_identifier(cls, process_group_identifier)

    @classmethod
    def patched_get_process_group(
        cls,
        process_group_id: str,
        find_direct_nested_items: bool = True,
        find_all_nested_items: bool = True,
        create_if_not_exists: bool = False,
    ):
        if is_super_admin_request() and has_request_context() and not getattr(g, "m8flow_tenant_id", None):
            base_dir = current_app.config.get("SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR")
            if isinstance(base_dir, str):
                _lock_super_admin_tenant_for_process_group(base_dir, process_group_id)
        return original_get_process_group(
            cls,
            process_group_id,
            find_direct_nested_items=find_direct_nested_items,
            find_all_nested_items=find_all_nested_items,
            create_if_not_exists=create_if_not_exists,
        )

    @classmethod
    def patched_save_process_model(cls, process_model: Any) -> None:
        if is_super_admin_request():
            raise ApiError("forbidden", SUPER_ADMIN_READ_ONLY_MESSAGE, status_code=403)
        return original_save_process_model(cls, process_model)

    @classmethod
    def patched_process_model_delete(cls, process_model_id: str) -> None:
        if is_super_admin_request():
            raise ApiError("forbidden", SUPER_ADMIN_READ_ONLY_MESSAGE, status_code=403)
        return original_process_model_delete(cls, process_model_id)

    @classmethod
    def patched_process_model_move(cls, original_process_model_id: str, new_location: str) -> Any:
        if is_super_admin_request():
            raise ApiError("forbidden", SUPER_ADMIN_READ_ONLY_MESSAGE, status_code=403)
        return original_process_model_move(cls, original_process_model_id, new_location)

    @classmethod
    def patched_copy_process_model(
        cls, original_process_model_id: str, new_process_model_id: str, new_display_name: str
    ) -> Any:
        if is_super_admin_request():
            raise ApiError("forbidden", SUPER_ADMIN_READ_ONLY_MESSAGE, status_code=403)
        return original_copy_process_model(cls, original_process_model_id, new_process_model_id, new_display_name)

    @classmethod
    def patched_add_process_group(cls, process_group: Any) -> Any:
        if is_super_admin_request():
            raise ApiError("forbidden", SUPER_ADMIN_READ_ONLY_MESSAGE, status_code=403)
        return original_add_process_group(cls, process_group)

    @classmethod
    def patched_update_process_group(cls, process_group: Any) -> Any:
        if is_super_admin_request():
            raise ApiError("forbidden", SUPER_ADMIN_READ_ONLY_MESSAGE, status_code=403)
        return original_update_process_group(cls, process_group)

    @classmethod
    def patched_process_group_move(cls, original_process_group_id: str, new_location: str) -> Any:
        if is_super_admin_request():
            raise ApiError("forbidden", SUPER_ADMIN_READ_ONLY_MESSAGE, status_code=403)
        return original_process_group_move(cls, original_process_group_id, new_location)

    @classmethod
    def patched_process_group_delete(cls, process_group_id: str) -> None:
        if is_super_admin_request():
            raise ApiError("forbidden", SUPER_ADMIN_READ_ONLY_MESSAGE, status_code=403)
        return original_process_group_delete(cls, process_group_id)

    ProcessModelService.get_process_groups_for_api = patched_get_process_groups_for_api
    ProcessModelService.get_process_models_for_api = patched_get_process_models_for_api
    ProcessModelService.get_process_model = patched_get_process_model
    ProcessModelService.is_process_model_identifier = patched_is_process_model_identifier
    ProcessModelService.is_process_group_identifier = patched_is_process_group_identifier
    ProcessModelService.get_process_group = patched_get_process_group
    ProcessModelService.save_process_model = patched_save_process_model
    ProcessModelService.process_model_delete = patched_process_model_delete
    ProcessModelService.process_model_move = patched_process_model_move
    ProcessModelService.copy_process_model = patched_copy_process_model
    ProcessModelService.add_process_group = patched_add_process_group
    ProcessModelService.update_process_group = patched_update_process_group
    ProcessModelService.process_group_move = patched_process_group_move
    ProcessModelService.process_group_delete = patched_process_group_delete

    _PATCHED = True
