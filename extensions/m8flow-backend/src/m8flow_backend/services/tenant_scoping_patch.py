# extensions/m8flow-backend/src/m8flow_backend/services/tenant_scoping_patch.py
from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from flask import g, has_request_context
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.orm import with_loader_criteria

from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin
from m8flow_backend.models.tenant_scoped import TenantScoped
from m8flow_backend.tenancy import (
    DEFAULT_TENANT_ID,
    LOGGER,
    allow_missing_tenant_context,
    get_context_tenant_id,
    get_tenant_id,
    is_public_request,
)

_ORIGINALS: dict[str, Any] = {}
_PATCHED = False

def _with_tenant(values: Mapping[str, Any] | Sequence[Mapping[str, Any]], tenant_id: str) -> Any:
    """Add tenant id to values if missing."""
    if isinstance(values, Mapping):
        if values.get("m8f_tenant_id"):
            return values
        updated = dict(values)
        updated["m8f_tenant_id"] = tenant_id
        return updated

    if isinstance(values, Sequence) and not isinstance(values, str | bytes):
        return [_with_tenant(value, tenant_id) for value in values]

    return values


def _set_tenant_on_objects(objects: Sequence[Any]) -> None:
    """Set tenant id on objects if missing."""
    if is_public_request():
        return
    tenant_id = get_tenant_id()
    for obj in objects:
        if hasattr(obj, "m8f_tenant_id") and not getattr(obj, "m8f_tenant_id"):
            setattr(obj, "m8f_tenant_id", tenant_id)


def _patch_bulk_save_objects() -> None:
    """Patch Session.bulk_save_objects to set tenant id on new objects."""
    if "bulk_save_objects" in _ORIGINALS:
        return

    _ORIGINALS["bulk_save_objects"] = Session.bulk_save_objects

    def patched_bulk_save_objects(self: Session, objects: Sequence[Any], *args: Any, **kwargs: Any) -> Any:
        _set_tenant_on_objects(objects)
        return _ORIGINALS["bulk_save_objects"](self, objects, *args, **kwargs)

    Session.bulk_save_objects = patched_bulk_save_objects  # type: ignore[assignment]


def _patch_insert_or_ignore_duplicate() -> None:
    """Patch insert_or_ignore_duplicate to add tenant scoping."""
    from spiffworkflow_backend.utils import db_utils

    if "insert_or_ignore_duplicate" in _ORIGINALS:
        return

    _ORIGINALS["insert_or_ignore_duplicate"] = db_utils.insert_or_ignore_duplicate

    def patched_insert_or_ignore_duplicate(
        model_class: type,
        values: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        postgres_conflict_index_elements: list[str],
    ) -> Any:
        """Insert record(s), ignoring duplicates, with tenant scoping."""
        if isinstance(model_class, type) and issubclass(model_class, TenantScoped):
            if is_public_request():
                return _ORIGINALS["insert_or_ignore_duplicate"](
                    model_class, values, postgres_conflict_index_elements
                )
            tenant_id = get_tenant_id()
            values_with_tenant = _with_tenant(values, tenant_id)
            conflict_elements = list(postgres_conflict_index_elements)
            if "m8f_tenant_id" not in conflict_elements:
                conflict_elements.insert(0, "m8f_tenant_id")
            return _ORIGINALS["insert_or_ignore_duplicate"](model_class, values_with_tenant, conflict_elements)
        return _ORIGINALS["insert_or_ignore_duplicate"](model_class, values, postgres_conflict_index_elements)

    db_utils.insert_or_ignore_duplicate = patched_insert_or_ignore_duplicate


def _patch_task_draft_data() -> None:
    """Patch TaskDraftDataModel insert to add tenant scoping."""
    from m8flow_backend.models.task_draft_data import TaskDraftDataModel

    if "task_draft_data_insert" in _ORIGINALS:
        return

    _ORIGINALS["task_draft_data_insert"] = TaskDraftDataModel.insert_or_update_task_draft_data_dict

    def patched_insert_or_update_task_draft_data_dict(task_draft_data_dict: dict[str, Any]) -> None:
        task_draft_data_dict = dict(task_draft_data_dict)
        if is_public_request():
            return _ORIGINALS["task_draft_data_insert"](task_draft_data_dict)
        if not task_draft_data_dict.get("m8f_tenant_id"):
            task_draft_data_dict["m8f_tenant_id"] = get_tenant_id()
        return _ORIGINALS["task_draft_data_insert"](task_draft_data_dict)

    TaskDraftDataModel.insert_or_update_task_draft_data_dict = staticmethod(patched_insert_or_update_task_draft_data_dict)


def _patch_task_instructions() -> None:
    """Patch TaskInstructionsForEndUserModel insert to add tenant scoping."""
    from m8flow_backend.models.task_instructions_for_end_user import TaskInstructionsForEndUserModel

    if "task_instructions_insert" in _ORIGINALS:
        return

    _ORIGINALS["task_instructions_insert"] = TaskInstructionsForEndUserModel.insert_or_update_record

    def patched_insert_or_update_record(task_guid: str, process_instance_id: int, instruction: str) -> None:
        """Insert task instruction record, ignoring duplicates, with tenant scoping."""
        import time

        from spiffworkflow_backend.models.db import db
        from m8flow_backend.models.task_instructions_for_end_user import TaskInstructionsForEndUserModel

        if is_public_request():
            return _ORIGINALS["task_instructions_insert"](task_guid, process_instance_id, instruction)
        tenant_id = get_tenant_id()
        record = [
            {
                "task_guid": task_guid,
                "process_instance_id": process_instance_id,
                "instruction": instruction,
                "timestamp": time.time(),
                "m8f_tenant_id": tenant_id,
            }
        ]
        dialect = db.engine.dialect.name
        if dialect == "mysql":
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            insert_stmt = mysql_insert(TaskInstructionsForEndUserModel).values(record)
            on_duplicate_key_stmt = insert_stmt.prefix_with("IGNORE")
        else:
            if dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                insert_stmt = sqlite_insert(TaskInstructionsForEndUserModel).values(record)
            else:
                from sqlalchemy.dialects.postgresql import insert as postgres_insert

                insert_stmt = postgres_insert(TaskInstructionsForEndUserModel).values(record)
            on_duplicate_key_stmt = insert_stmt.on_conflict_do_nothing(index_elements=["task_guid"])
        db.session.execute(on_duplicate_key_stmt)

    TaskInstructionsForEndUserModel.insert_or_update_record = staticmethod(patched_insert_or_update_record)


def _patch_future_task() -> None:
    """Patch FutureTaskModel insert_or_update to add tenant scoping."""
    from m8flow_backend.models.future_task import FutureTaskModel

    if "future_task_insert" in _ORIGINALS:
        return

    _ORIGINALS["future_task_insert"] = FutureTaskModel.insert_or_update

    def patched_insert_or_update(guid: str, run_at_in_seconds: int, queued_to_run_at_in_seconds: int | None = None) -> None:
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.models.future_task import FutureTaskModel
        from sqlalchemy.dialects.mysql import insert as mysql_insert
        from sqlalchemy.dialects.postgresql import insert as postgres_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        import time

        if is_public_request():
            return _ORIGINALS["future_task_insert"](guid, run_at_in_seconds, queued_to_run_at_in_seconds)
        tenant_id = get_tenant_id()
        task_info: dict[str, int | str | None] = {
            "guid": guid,
            "run_at_in_seconds": run_at_in_seconds,
            "updated_at_in_seconds": round(time.time()),
            "m8f_tenant_id": tenant_id,
        }
        if queued_to_run_at_in_seconds is not None:
            task_info["queued_to_run_at_in_seconds"] = queued_to_run_at_in_seconds

        new_values = dict(task_info)
        del new_values["guid"]

        dialect = db.engine.dialect.name
        if dialect == "mysql":
            insert_stmt = mysql_insert(FutureTaskModel).values(task_info)
            on_duplicate_key_stmt = insert_stmt.on_duplicate_key_update(**new_values)
        else:
            if dialect == "sqlite":
                insert_stmt = sqlite_insert(FutureTaskModel).values(task_info)
            else:
                insert_stmt = postgres_insert(FutureTaskModel).values(task_info)
            on_duplicate_key_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["guid"],
                set_=new_values,
            )
        db.session.execute(on_duplicate_key_stmt)

    FutureTaskModel.insert_or_update = staticmethod(patched_insert_or_update)


def _patch_process_caller_relationship() -> None:
    """Patch ProcessCallerRelationshipModel insert_or_update to add tenant scoping."""
    from m8flow_backend.models.process_caller_relationship import ProcessCallerRelationshipModel

    if "process_caller_relationship_insert" in _ORIGINALS:
        return

    _ORIGINALS["process_caller_relationship_insert"] = ProcessCallerRelationshipModel.insert_or_update

    def patched_insert_or_update(called_reference_cache_process_id: int, calling_reference_cache_process_id: int) -> None:
        from spiffworkflow_backend.models.db import db
        from m8flow_backend.models.process_caller_relationship import ProcessCallerRelationshipModel
        from sqlalchemy.dialects.mysql import insert as mysql_insert
        from sqlalchemy.dialects.postgresql import insert as postgres_insert

        if is_public_request():
            return _ORIGINALS["process_caller_relationship_insert"](
                called_reference_cache_process_id, calling_reference_cache_process_id
            )
        tenant_id = get_tenant_id()
        caller_info = {
            "called_reference_cache_process_id": called_reference_cache_process_id,
            "calling_reference_cache_process_id": calling_reference_cache_process_id,
            "m8f_tenant_id": tenant_id,
        }
        dialect = db.engine.dialect.name
        if dialect == "mysql":
            insert_stmt = mysql_insert(ProcessCallerRelationshipModel).values(caller_info)
            on_duplicate_key_stmt = insert_stmt.on_duplicate_key_update(
                called_reference_cache_process_id=insert_stmt.inserted.called_reference_cache_process_id
            )
        else:
            if dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                insert_stmt = sqlite_insert(ProcessCallerRelationshipModel).values(caller_info)
            else:
                insert_stmt = postgres_insert(ProcessCallerRelationshipModel).values(caller_info)
            on_duplicate_key_stmt = insert_stmt.on_conflict_do_nothing(
                index_elements=["called_reference_cache_process_id", "calling_reference_cache_process_id"]
            )
        db.session.execute(on_duplicate_key_stmt)

    ProcessCallerRelationshipModel.insert_or_update = staticmethod(patched_insert_or_update)


def _patch_reference_cache_basic_query() -> None:
    """Patch ReferenceCacheModel.basic_query to scope by tenant and max generation id."""
    from m8flow_backend.models.reference_cache import ReferenceCacheModel
    from spiffworkflow_backend.models.db import db

    if "reference_cache_basic_query" in _ORIGINALS:
        return

    _ORIGINALS["reference_cache_basic_query"] = ReferenceCacheModel.basic_query

    def patched_basic_query(cls: type) -> Any:
        if is_public_request():
            return _ORIGINALS["reference_cache_basic_query"](cls)
        tenant_id = get_tenant_id()
        max_generation_id = (
            db.session.query(db.func.max(ReferenceCacheModel.generation_id))
            .filter(ReferenceCacheModel.m8f_tenant_id == tenant_id)  # type: ignore[attr-defined]
            .scalar()
        )
        basic_query = cls.query
        if max_generation_id is not None:
            basic_query = basic_query.filter_by(generation_id=max_generation_id)
        return basic_query

    ReferenceCacheModel.basic_query = classmethod(patched_basic_query)


@event.listens_for(Session, "before_flush")  # type: ignore[misc]
def _set_tenant_on_flush(session: Session, _flush_context: Any, _instances: Any) -> None:
    """Set tenant id on objects if missing."""
    if is_public_request():
        return
    for obj in session.new:
        if hasattr(obj, "m8f_tenant_id") and not getattr(obj, "m8f_tenant_id"):
            setattr(obj, "m8f_tenant_id", get_tenant_id())


def _tenant_scope_queries(execute_state: Any) -> None:
    """Apply tenant scoping to all queries for TenantScoped models."""
    if is_public_request():
        return
    if not execute_state.is_select:
        return

    # Don't scope queries that are reading the tenant table itself
    # (otherwise resolve_request_tenant() tries to validate tenant_id using a
    # query that requires tenant_id -> circular dependency in tests)
    try:
        stmt = execute_state.statement
        for from_ in stmt.get_final_froms():
            if getattr(from_, "name", None) == "m8flow_tenant":
                return
    except Exception:
        # if statement shape is unexpected, fail open (don't break the query)
        pass

    # Background/scheduled jobs may run outside a request context. In that case, we either:
    # - use a context tenant if one was set, or
    # - fall back to DEFAULT_TENANT_ID (see _resolve_tenant_id_for_db()).
    #
    # If we still can't resolve (e.g. request context missing and strict mode), fail open
    # so background processing doesn't crash the whole scheduler loop.
    try:
        tenant_id = _resolve_tenant_id_for_db()
    except RuntimeError:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            M8fTenantScopedMixin,
            lambda cls: cls.m8f_tenant_id == tenant_id,
            include_aliases=True,
            track_closure_variables=True,
        )
    )



def _resolve_tenant_id_for_db() -> str:
    if has_request_context():
        if getattr(g, "m8flow_tenant_id", None):
            return get_tenant_id()
        if allow_missing_tenant_context():
            return DEFAULT_TENANT_ID
        raise RuntimeError("Missing tenant context for database session.")

    context_tid = get_context_tenant_id()
    if context_tid:
        return context_tid

    if allow_missing_tenant_context():
        return DEFAULT_TENANT_ID

    # Background jobs have no request/context tenant; use default tenant (matches get_tenant_id()).
    return DEFAULT_TENANT_ID


@event.listens_for(Session, "after_begin")  # type: ignore[misc]
def _set_postgres_tenant_context(session: Session, transaction: Any, connection: Any) -> None:
    if is_public_request():
        return
    if connection.dialect.name != "postgresql":
        return

    # During early request handling (e.g. omni_auth token verification), DB access can happen
    # before tenant resolution middleware has run. In that case we fail open (skip setting the
    # per-transaction tenant) rather than crashing the request.
    try:
        tenant_id = _resolve_tenant_id_for_db()
    except RuntimeError:
        return
    connection.exec_driver_sql(
        "SET LOCAL app.current_tenant = %s",
        (tenant_id,),
    )


_SCOPING_LISTENER_REGISTERED = False

def apply() -> None:
    global _SCOPING_LISTENER_REGISTERED
    if not _SCOPING_LISTENER_REGISTERED:
        event.listen(Session, "do_orm_execute", _tenant_scope_queries)
        _SCOPING_LISTENER_REGISTERED = True
    global _PATCHED
    if _PATCHED:
        return

    _patch_bulk_save_objects()
    _patch_insert_or_ignore_duplicate()
    _patch_task_draft_data()
    _patch_task_instructions()
    _patch_future_task()
    _patch_process_caller_relationship()
    _patch_reference_cache_basic_query()

    _PATCHED = True
    LOGGER.info("M8FLOW tenant scoping patch applied")


def reset() -> None:
    """Remove global SQLAlchemy listeners so tests don't leak state."""
    global _SCOPING_LISTENER_REGISTERED
    if _SCOPING_LISTENER_REGISTERED:
        event.remove(Session, "do_orm_execute", _tenant_scope_queries)
        _SCOPING_LISTENER_REGISTERED = False
