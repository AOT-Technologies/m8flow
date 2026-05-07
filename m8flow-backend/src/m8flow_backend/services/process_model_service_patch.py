from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from flask import g, has_request_context

from m8flow_backend.tenancy import reset_context_tenant_id, set_context_tenant_id
from m8flow_backend.tenancy import is_super_admin_request

_PATCHED = False
_ORIGINAL_METHODS: dict[str, Any] = {}


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
    for tenant_id in _tenant_roots(base_dir):
        candidate = os.path.join(base_dir, tenant_id, rel, FileSystemService.PROCESS_MODEL_JSON_FILE)
        if os.path.isfile(candidate):
            g.m8flow_tenant_id = tenant_id
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
    for tenant_id in _tenant_roots(base_dir):
        candidate = os.path.join(base_dir, tenant_id, rel, FileSystemService.PROCESS_GROUP_JSON_FILE)
        if os.path.isfile(candidate):
            g.m8flow_tenant_id = tenant_id
            set_context_tenant_id(tenant_id)
            return


@contextmanager
def _temporary_tenant_context(tenant_id: str):
    prev_request_tenant = getattr(g, "m8flow_tenant_id", None) if has_request_context() else None
    token = set_context_tenant_id(tenant_id)
    try:
        if has_request_context():
            g.m8flow_tenant_id = tenant_id
        yield
    finally:
        reset_context_tenant_id(token)
        if has_request_context():
            if prev_request_tenant is None:
                if hasattr(g, "m8flow_tenant_id"):
                    delattr(g, "m8flow_tenant_id")
            else:
                g.m8flow_tenant_id = prev_request_tenant


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from flask import current_app
    from spiffworkflow_backend.services.process_model_service import ProcessModelService

    _ORIGINAL_METHODS["get_process_groups_for_api"] = ProcessModelService.get_process_groups_for_api
    _ORIGINAL_METHODS["get_process_models_for_api"] = ProcessModelService.get_process_models_for_api
    _ORIGINAL_METHODS["get_process_model"] = ProcessModelService.get_process_model
    _ORIGINAL_METHODS["is_process_model_identifier"] = ProcessModelService.is_process_model_identifier
    _ORIGINAL_METHODS["is_process_group_identifier"] = ProcessModelService.is_process_group_identifier
    _ORIGINAL_METHODS["get_process_group"] = ProcessModelService.get_process_group

    original_get_process_groups_for_api = ProcessModelService.get_process_groups_for_api.__func__
    original_get_process_models_for_api = ProcessModelService.get_process_models_for_api.__func__
    original_get_process_model = ProcessModelService.get_process_model.__func__
    original_is_process_model_identifier = ProcessModelService.is_process_model_identifier.__func__
    original_is_process_group_identifier = ProcessModelService.is_process_group_identifier.__func__
    original_get_process_group = ProcessModelService.get_process_group.__func__

    @classmethod
    def patched_get_process_groups_for_api(
        cls,
        process_group_id: str | None = None,
        user: Any | None = None,
    ):
        if not is_super_admin_request():
            return original_get_process_groups_for_api(cls, process_group_id=process_group_id, user=user)

        base_dir = current_app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"]
        tenant_ids = _tenant_roots(base_dir)
        merged: list[Any] = []
        seen: set[str] = set()

        for tenant_id in tenant_ids:
            with _temporary_tenant_context(tenant_id):
                groups = original_get_process_groups_for_api(cls, process_group_id=process_group_id, user=user)
                for group in groups:
                    group_id = getattr(group, "id", None)
                    if isinstance(group_id, str) and group_id in seen:
                        continue
                    if isinstance(group_id, str):
                        seen.add(group_id)
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
    ):
        if not is_super_admin_request():
            return original_get_process_models_for_api(
                cls,
                user=user,
                process_group_id=process_group_id,
                recursive=recursive,
                filter_runnable_by_user=filter_runnable_by_user,
                filter_runnable_as_extension=filter_runnable_as_extension,
                include_files=include_files,
            )

        base_dir = current_app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"]
        tenant_ids = _tenant_roots(base_dir)
        merged: list[Any] = []
        seen: set[str] = set()

        for tenant_id in tenant_ids:
            with _temporary_tenant_context(tenant_id):
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

    ProcessModelService.get_process_groups_for_api = patched_get_process_groups_for_api
    ProcessModelService.get_process_models_for_api = patched_get_process_models_for_api
    ProcessModelService.get_process_model = patched_get_process_model
    ProcessModelService.is_process_model_identifier = patched_is_process_model_identifier
    ProcessModelService.is_process_group_identifier = patched_is_process_group_identifier
    ProcessModelService.get_process_group = patched_get_process_group

    _PATCHED = True
