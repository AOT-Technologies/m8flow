# m8flow-backend/src/m8flow_backend/services/process_model_soft_delete_patch.py
"""Soft-delete patch for process models and process groups.

Instead of hard-deleting (shutil.rmtree) entities, this patch marks them
as ``is_deleted = True`` in their on-disk JSON metadata.  Scan/list methods
are wrapped so that deleted entities are transparently filtered out of all
API responses.

The ``created_by`` field is injected into the creation controllers so every
new entity records its author for audit purposes.

Process instances belonging to soft-deleted models are also transparently
filtered from all list/report queries.

Only the m8flow layer is modified — upstream spiffworkflow-backend is
monkey-patched at runtime.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

_PATCHED = False
LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1.  Data-model extension helpers
# ---------------------------------------------------------------------------

def _extend_list_if_missing(target_list: list, *items: str) -> None:
    """Append items to *target_list* only when they are not already present."""
    for item in items:
        if item not in target_list:
            target_list.append(item)


def _inject_dataclass_field(cls: type, name: str, default: Any) -> None:
    """Add a dataclass-style attribute with a default to *cls*.

    Because upstream dataclasses are already frozen by ``@dataclass``, we
    cannot call ``dataclasses.field`` after the fact.  Instead we set a
    class-level default and patch ``__init__`` so that the field is accepted
    as an optional kwarg.
    """
    if hasattr(cls, name):
        return  # already injected (idempotent)

    setattr(cls, name, default)

    original_init = cls.__init__

    def _new_init(self: Any, *args: Any, **kwargs: Any) -> None:
        value = kwargs.pop(name, default)
        original_init(self, *args, **kwargs)
        object.__setattr__(self, name, value) if dataclasses.is_dataclass(self) else setattr(self, name, value)

    cls.__init__ = _new_init  # type: ignore[attr-defined]

    # Also patch to_dict / serialized so the field appears in API responses
    # and disk writes.
    _patch_serialization(cls, name)


def _patch_serialization(cls: type, field_name: str) -> None:
    """Ensure *field_name* appears in ``to_dict`` / ``serialized`` output."""
    for method_name in ("to_dict", "serialized"):
        original_method = getattr(cls, method_name, None)
        if original_method is None:
            continue

        # Guard against double-patching the same field
        marker = f"_soft_delete_patched_{method_name}_{field_name}"
        if getattr(original_method, marker, False):
            continue

        def _make_wrapper(orig, fname, mname):  # noqa: B023 – closure capture
            def wrapper(self, *args, **kwargs):
                result = orig(self, *args, **kwargs)
                if isinstance(result, dict):
                    result[fname] = getattr(self, fname, None)
                return result
            # Copy metadata so we look like the original
            wrapper.__name__ = mname
            setattr(wrapper, f"_soft_delete_patched_{mname}_{fname}", True)
            return wrapper

        setattr(cls, method_name, _make_wrapper(original_method, field_name, method_name))


def _patch_deserialization(cls: type, *field_names: str) -> None:
    """Patch ``from_dict``, ``get_valid_properties``, and ``restrict_dict``
    on *cls* so that runtime-injected fields are recognized during read-back.

    The upstream code uses ``dataclasses.fields(cls)`` and
    ``cls.__dataclass_fields__`` to build allow-lists.  Our injected fields
    are not real dataclass fields, so they get silently dropped.  We fix
    this by wrapping the relevant methods.
    """
    # --- from_dict ---
    original_from_dict = getattr(cls, "from_dict", None)
    if original_from_dict and not getattr(original_from_dict, "_soft_delete_patched_from_dict", False):
        @classmethod  # type: ignore[misc]
        def _patched_from_dict(klass, data: dict[str, Any], _orig=original_from_dict, _extra=field_names):
            obj = _orig.__func__(klass, data) if hasattr(_orig, '__func__') else _orig(data)
            # Re-apply fields that from_dict may have stripped
            for fname in _extra:
                if fname in data and not hasattr(obj, fname):
                    object.__setattr__(obj, fname, data[fname]) if dataclasses.is_dataclass(obj) else setattr(obj, fname, data[fname])
                elif fname in data:
                    # The attribute exists (from __init__ patch) but may
                    # have the default value because from_dict filtered it.
                    current = getattr(obj, fname, None)
                    desired = data[fname]
                    if current != desired:
                        object.__setattr__(obj, fname, desired) if dataclasses.is_dataclass(obj) else setattr(obj, fname, desired)
            return obj
        _patched_from_dict._soft_delete_patched_from_dict = True  # type: ignore[attr-defined]
        cls.from_dict = _patched_from_dict

    # --- get_valid_properties ---
    original_gvp = getattr(cls, "get_valid_properties", None)
    if original_gvp and not getattr(original_gvp, "_soft_delete_patched_gvp", False):
        @classmethod  # type: ignore[misc]
        def _patched_gvp(klass, _orig=original_gvp, _extra=field_names):
            props = _orig.__func__(klass) if hasattr(_orig, '__func__') else _orig()
            for fname in _extra:
                if fname not in props:
                    props.append(fname)
            return props
        _patched_gvp._soft_delete_patched_gvp = True  # type: ignore[attr-defined]
        cls.get_valid_properties = _patched_gvp


# ---------------------------------------------------------------------------
# 2.  Service monkey-patches
# ---------------------------------------------------------------------------

def _soft_delete_process_model(cls: type, process_model_id: str) -> None:
    """Replace hard-delete with a soft-delete flag."""
    from flask import current_app, g

    process_model = cls.get_process_model(process_model_id)
    process_model.is_deleted = True

    # Persist via normal save path (respects serialisation keys)
    cls.save_process_model(process_model)

    username = getattr(g, "user", None)
    username = getattr(username, "username", "unknown") if username else "unknown"
    current_app.logger.info(
        "SOFT_DELETE | entity_type=process_model | entity_id=%s | deleted_by=%s | timestamp=%s",
        process_model_id,
        username,
        datetime.now(timezone.utc).isoformat(),
    )


def _soft_delete_process_group(cls: type, process_group_id: str) -> None:
    """Replace hard-delete with a soft-delete flag (group + nested models)."""
    from flask import current_app, g

    process_group = cls.get_process_group(process_group_id)
    process_group.is_deleted = True

    # Also mark every nested model as deleted
    for pm in getattr(process_group, "process_models", []) or []:
        pm.is_deleted = True
        cls.save_process_model(pm)

    # Recursively soft-delete nested sub-groups
    for pg in getattr(process_group, "process_groups", []) or []:
        _soft_delete_process_group(cls, pg.id)

    cls.update_process_group(process_group)

    username = getattr(g, "user", None)
    username = getattr(username, "username", "unknown") if username else "unknown"
    current_app.logger.info(
        "SOFT_DELETE | entity_type=process_group | entity_id=%s | deleted_by=%s | timestamp=%s",
        process_group_id,
        username,
        datetime.now(timezone.utc).isoformat(),
    )


def _wrap_find_or_create_process_group(original_fn):
    """After loading a process group, filter out soft-deleted children."""
    def wrapper(dir_path, find_direct_nested_items=True, find_all_nested_items=True):
        process_group = original_fn(
            dir_path,
            find_direct_nested_items=find_direct_nested_items,
            find_all_nested_items=find_all_nested_items,
        )
        # Filter out deleted nested models
        if hasattr(process_group, "process_models") and process_group.process_models:
            process_group.process_models = [
                pm for pm in process_group.process_models
                if not getattr(pm, "is_deleted", False)
            ]
        # Filter out deleted nested groups
        if hasattr(process_group, "process_groups") and process_group.process_groups:
            process_group.process_groups = [
                pg for pg in process_group.process_groups
                if not getattr(pg, "is_deleted", False)
            ]
        return process_group
    return wrapper


def _wrap_scan_process_model(original_fn):
    """After scanning a process model, just return it as-is.

    Soft-deleted models are filtered out at the group level by
    ``_wrap_find_or_create_process_group``.  We must NOT raise here
    because ``find_or_create_process_group`` calls ``__scan_process_model``
    inside a loop that builds a list — raising would break the entire scan.
    """
    def wrapper(path, name=None):
        return original_fn(path, name=name)
    return wrapper


def _wrap_get_process_model(original_fn):
    """Silently handle direct access to a soft-deleted process model.

    When the process-instances page (or any other caller) tries to load
    a model that has been soft-deleted, we return the model with a
    "[Deleted]" marker instead of letting errors bubble up.
    """
    def wrapper(cls, process_model_id):
        process_model = original_fn(cls, process_model_id)
        if getattr(process_model, "is_deleted", False):
            LOGGER.info(
                "get_process_model: suppressed soft-deleted model %s",
                process_model_id,
            )
            # Return the model but mark display_name so it's obvious
            process_model.display_name = f"{process_model.display_name} [Deleted]"
        return process_model
    return wrapper


def _wrap_scan_process_groups(original_fn):
    """After scanning process groups, filter out soft-deleted ones."""
    def wrapper(process_group_id=None):
        groups = original_fn(process_group_id)
        return [
            g for g in groups
            if not getattr(g, "is_deleted", False)
        ]
    return wrapper


def _collect_soft_deleted_model_ids() -> set[str]:
    """Walk every process model on disk and return IDs where is_deleted is True.

    This is called once during the report-query patch so that process
    instances belonging to deleted models can be excluded from listings.
    """
    from spiffworkflow_backend.services.file_system_service import FileSystemService
    from spiffworkflow_backend.services.process_model_service import ProcessModelService

    deleted_ids: set[str] = set()
    root = FileSystemService.root_path()
    if not os.path.exists(root):
        return deleted_ids

    for dirpath, _dirs, files in os.walk(root):
        if ProcessModelService.PROCESS_MODEL_JSON_FILE in files:
            json_path = os.path.join(dirpath, ProcessModelService.PROCESS_MODEL_JSON_FILE)
            try:
                with open(json_path) as f:
                    data = json.load(f)
                if data.get("is_deleted"):
                    relative = os.path.relpath(dirpath, root)
                    model_id = ProcessModelService.path_to_id(relative)
                    deleted_ids.add(model_id)
            except Exception:
                pass
    return deleted_ids


# ---------------------------------------------------------------------------
# 3.  Controller monkey-patches  (inject created_by)
# ---------------------------------------------------------------------------

def _wrap_process_model_create(original_fn):
    """Inject ``created_by`` into the body before creating a process model."""
    def wrapper(modified_process_group_id, body):
        from flask import g
        body["created_by"] = getattr(getattr(g, "user", None), "username", None)
        return original_fn(modified_process_group_id, body)
    return wrapper


def _wrap_process_model_create_with_nl(original_fn):
    """Inject ``created_by`` for natural-language creation."""
    def wrapper(modified_process_group_id, body):
        from flask import g
        body["created_by"] = getattr(getattr(g, "user", None), "username", None)
        return original_fn(modified_process_group_id, body)
    return wrapper


def _wrap_process_group_create(original_fn):
    """Inject ``created_by`` into the body before creating a process group."""
    def wrapper(body):
        from flask import g
        body["created_by"] = getattr(getattr(g, "user", None), "username", None)
        return original_fn(body)
    return wrapper


# ---------------------------------------------------------------------------
# 4.  Main apply entry point
# ---------------------------------------------------------------------------

def apply() -> None:  # noqa: C901 – complexity is justified for a single-file patch
    global _PATCHED
    if _PATCHED:
        return

    # -- Import upstream modules ------------------------------------------------
    from spiffworkflow_backend.models import process_model as pm_module
    from spiffworkflow_backend.models import process_group as pg_module
    from spiffworkflow_backend.models.process_model import ProcessModelInfo
    from spiffworkflow_backend.models.process_group import ProcessGroup
    from spiffworkflow_backend.services.process_model_service import ProcessModelService
    from spiffworkflow_backend.routes import process_models_controller as pmc
    from spiffworkflow_backend.routes import process_groups_controller as pgc

    # -- 1. Extend serialization key lists --------------------------------------
    _extend_list_if_missing(
        pm_module.PROCESS_MODEL_SUPPORTED_KEYS_FOR_DISK_SERIALIZATION,
        "is_deleted",
        "created_by",
    )
    _extend_list_if_missing(
        pg_module.PROCESS_GROUP_SUPPORTED_KEYS_FOR_DISK_SERIALIZATION,
        "is_deleted",
        "created_by",
    )
    _extend_list_if_missing(
        pg_module.PROCESS_GROUP_KEYS_TO_UPDATE_FROM_API,
        "is_deleted",
        "created_by",
    )

    # -- 2. Inject dataclass fields --------------------------------------------
    _inject_dataclass_field(ProcessModelInfo, "is_deleted", False)
    _inject_dataclass_field(ProcessModelInfo, "created_by", None)
    _inject_dataclass_field(ProcessGroup, "is_deleted", False)
    _inject_dataclass_field(ProcessGroup, "created_by", None)

    # -- 2b. Patch deserialization so injected fields survive read-back ----------
    # Without this, from_dict / get_valid_properties / restrict_dict silently
    # strip ``is_deleted`` and ``created_by`` because they are not real
    # dataclass fields (they were added at runtime).
    _patch_deserialization(ProcessGroup, "is_deleted", "created_by")
    _patch_deserialization(ProcessModelInfo, "is_deleted", "created_by")

    # -- 3. Patch service methods ----------------------------------------------
    ProcessModelService.process_model_delete = classmethod(  # type: ignore[assignment]
        lambda cls, pid: _soft_delete_process_model(cls, pid)
    )
    ProcessModelService.process_group_delete = classmethod(  # type: ignore[assignment]
        lambda cls, gid: _soft_delete_process_group(cls, gid)
    )

    # Wrap find_or_create_process_group (classmethod)
    original_find_or_create = ProcessModelService.find_or_create_process_group.__func__  # type: ignore[attr-defined]
    ProcessModelService.find_or_create_process_group = classmethod(  # type: ignore[assignment]
        lambda cls, *a, **kw: _wrap_find_or_create_process_group(
            lambda *ia, **ik: original_find_or_create(cls, *ia, **ik)
        )(*a, **kw)
    )

    # Wrap __scan_process_model (name-mangled private classmethod)
    mangled_scan_model = "_ProcessModelService__scan_process_model"
    original_scan_model = getattr(ProcessModelService, mangled_scan_model).__func__
    wrapped_scan_model = _wrap_scan_process_model(
        lambda *a, **kw: original_scan_model(ProcessModelService, *a, **kw)
    )
    setattr(
        ProcessModelService,
        mangled_scan_model,
        classmethod(lambda cls, *a, **kw: wrapped_scan_model(*a, **kw)),
    )

    # Wrap __scan_process_groups (name-mangled private classmethod)
    mangled_scan_groups = "_ProcessModelService__scan_process_groups"
    original_scan_groups = getattr(ProcessModelService, mangled_scan_groups).__func__
    wrapped_scan_groups = _wrap_scan_process_groups(
        lambda *a, **kw: original_scan_groups(ProcessModelService, *a, **kw)
    )
    setattr(
        ProcessModelService,
        mangled_scan_groups,
        classmethod(lambda cls, *a, **kw: wrapped_scan_groups(*a, **kw)),
    )

    # Wrap get_process_model so direct lookups of soft-deleted models don't
    # raise ProcessEntityNotFoundError (which surfaces as a browser alert).
    original_get_process_model = ProcessModelService.get_process_model.__func__  # type: ignore[attr-defined]
    wrapped_get_process_model = _wrap_get_process_model(original_get_process_model)
    ProcessModelService.get_process_model = classmethod(  # type: ignore[assignment]
        lambda cls, *a, **kw: wrapped_get_process_model(cls, *a, **kw)
    )

    # -- 4. Patch controllers --------------------------------------------------
    pmc.process_model_create = _wrap_process_model_create(pmc.process_model_create)
    pmc.process_model_create_with_natural_language = _wrap_process_model_create_with_nl(
        pmc.process_model_create_with_natural_language
    )
    pgc.process_group_create = _wrap_process_group_create(pgc.process_group_create)

    # -- 5. Patch process instance queries to exclude soft-deleted models -------
    _patch_process_instance_queries()

    _PATCHED = True
    LOGGER.info("process_model_soft_delete_patch: applied successfully")


def _patch_process_instance_queries() -> None:
    """Filter process instances of soft-deleted models from report queries.

    The process instance list is generated via
    ``ProcessInstanceReportService.run_process_instance_report`` which calls
    ``get_basic_query``.  We wrap that method (or the m8flow-patched version
    if it already exists) to add a NOT-IN filter for deleted model ids.
    """
    from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
    from spiffworkflow_backend.services.process_instance_report_service import ProcessInstanceReportService

    original_get_basic_query = ProcessInstanceReportService.get_basic_query

    @classmethod  # type: ignore[misc]
    def _filtered_get_basic_query(cls, filters):
        query = original_get_basic_query.__func__(cls, filters) if hasattr(original_get_basic_query, '__func__') else original_get_basic_query(filters)
        # Collect soft-deleted model IDs and exclude their instances
        deleted_ids = _collect_soft_deleted_model_ids()
        if deleted_ids:
            query = query.filter(
                ProcessInstanceModel.process_model_identifier.notin_(deleted_ids)  # type: ignore[union-attr]
            )
        return query

    ProcessInstanceReportService.get_basic_query = _filtered_get_basic_query
