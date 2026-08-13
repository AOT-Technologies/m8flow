# m8flow-backend/src/m8flow_backend/models/tenant_schema.py
"""m8flow's ORM delta over upstream SpiffArena, declared one model at a time.

Augments upstream's mapped classes in place: appends m8flow's columns to their
Table, maps them onto their Mapper, and redefines the constraints m8flow changes.
No database work happens here - the Alembic migrations own the physical schema and
PostgreSQL RLS owns tenant isolation; this only teaches SQLAlchemy about them.

Usage - import the models, then call ``configure()``::

    import spiffworkflow_backend.load_database_models
    tenant_schema.configure()

The app's patch registry, ``migrations/env.py`` and ``bin/dump-model-metadata.py``
each do that.

To add a schema change, add the model to a tuple below (or give it its own
``_extend_*`` function) and write the migration that makes the same change in the
database.
"""
from __future__ import annotations

import logging

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy import UniqueConstraint

from spiffworkflow_backend.models.api_log_model import APILogModel
from spiffworkflow_backend.models.bpmn_process import BpmnProcessModel
from spiffworkflow_backend.models.bpmn_process_definition import BpmnProcessDefinitionModel
from spiffworkflow_backend.models.bpmn_process_definition_relationship import (
    BpmnProcessDefinitionRelationshipModel,
)
from spiffworkflow_backend.models.configuration import ConfigurationModel
from spiffworkflow_backend.models.future_task import FutureTaskModel
from spiffworkflow_backend.models.human_task import HumanTaskModel
from spiffworkflow_backend.models.human_task_user import HumanTaskUserModel
from spiffworkflow_backend.models.json_data_store import JSONDataStoreModel
from spiffworkflow_backend.models.kkv_data_store import KKVDataStoreModel
from spiffworkflow_backend.models.kkv_data_store_entry import KKVDataStoreEntryModel
from spiffworkflow_backend.models.message_instance import MessageInstanceModel
from spiffworkflow_backend.models.message_instance_correlation import (
    MessageInstanceCorrelationRuleModel,
)
from spiffworkflow_backend.models.message_model import MessageCorrelationPropertyModel
from spiffworkflow_backend.models.message_model import MessageModel
from spiffworkflow_backend.models.message_triggerable_process_model import (
    MessageTriggerableProcessModel,
)
from spiffworkflow_backend.models.permission_assignment import PermissionAssignmentModel
from spiffworkflow_backend.models.permission_target import PermissionTargetModel
from spiffworkflow_backend.models.pkce_code_verifier import PkceCodeVerifierModel
from spiffworkflow_backend.models.process_caller import ProcessCallerCacheModel
from spiffworkflow_backend.models.process_caller_relationship import ProcessCallerRelationshipModel
from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
from spiffworkflow_backend.models.process_instance_error_detail import ProcessInstanceErrorDetailModel
from spiffworkflow_backend.models.process_instance_event import ProcessInstanceEventModel
from spiffworkflow_backend.models.process_instance_file_data import ProcessInstanceFileDataModel
from spiffworkflow_backend.models.process_instance_metadata import ProcessInstanceMetadataModel
from spiffworkflow_backend.models.process_instance_migration_detail import (
    ProcessInstanceMigrationDetailModel,
)
from spiffworkflow_backend.models.process_instance_queue import ProcessInstanceQueueModel
from spiffworkflow_backend.models.process_instance_report import ProcessInstanceReportModel
from spiffworkflow_backend.models.process_model_cycle import ProcessModelCycleModel
from spiffworkflow_backend.models.reference_cache import ReferenceCacheModel
from spiffworkflow_backend.models.refresh_token import RefreshTokenModel
from spiffworkflow_backend.models.secret_model import SecretModel
from spiffworkflow_backend.models.service_account import ServiceAccountModel
from spiffworkflow_backend.models.task import TaskModel
from spiffworkflow_backend.models.task_definition import TaskDefinitionModel
from spiffworkflow_backend.models.task_draft_data import TaskDraftDataModel
from spiffworkflow_backend.models.task_instructions_for_end_user import (
    TaskInstructionsForEndUserModel,
)
from spiffworkflow_backend.models.typeahead import TypeaheadModel
from spiffworkflow_backend.models.user import UserModel

LOGGER = logging.getLogger(__name__)

TENANT_COLUMN = "m8f_tenant_id"
TENANT_FK = "m8flow_tenant.id"


# ---------------------------------------------------------------------------
# The registries
# ---------------------------------------------------------------------------

#: Models whose table gains ``m8f_tenant_id``.
#: ``UserModel``, ``PermissionTargetModel`` and ``PermissionAssignmentModel`` are
#: deliberately absent: users and permissions are shared across tenants.
TENANT_SCOPED_MODELS: tuple[type, ...] = (
    APILogModel,
    BpmnProcessDefinitionModel,
    BpmnProcessDefinitionRelationshipModel,
    BpmnProcessModel,
    ConfigurationModel,
    FutureTaskModel,
    HumanTaskModel,
    HumanTaskUserModel,
    JSONDataStoreModel,
    KKVDataStoreEntryModel,
    KKVDataStoreModel,
    MessageCorrelationPropertyModel,
    MessageInstanceCorrelationRuleModel,
    MessageInstanceModel,
    MessageModel,
    MessageTriggerableProcessModel,
    PkceCodeVerifierModel,
    ProcessCallerCacheModel,
    ProcessCallerRelationshipModel,
    ProcessInstanceErrorDetailModel,
    ProcessInstanceEventModel,
    ProcessInstanceFileDataModel,
    ProcessInstanceMetadataModel,
    ProcessInstanceMigrationDetailModel,
    ProcessInstanceModel,
    ProcessInstanceQueueModel,
    ProcessInstanceReportModel,
    ProcessModelCycleModel,
    ReferenceCacheModel,
    RefreshTokenModel,
    SecretModel,
    ServiceAccountModel,
    TaskDefinitionModel,
    TaskDraftDataModel,
    TaskInstructionsForEndUserModel,
    TaskModel,
    TypeaheadModel,
)

#: Upstream composite UNIQUE constraints that have to include the tenant column,
#: or two tenants could not hold the same value.  The name is kept so the
#: constraint keeps matching what the migrations created.
#: ``(model, constraint name, upstream columns)``
TENANT_SCOPED_UNIQUES: tuple[tuple[type, str, tuple[str, ...]], ...] = (
    (
        BpmnProcessDefinitionModel,
        "process_hash_unique",
        ("full_process_model_hash", "single_process_hash"),
    ),
    (JSONDataStoreModel, "_identifier_location_unique", ("identifier", "location")),
    (KKVDataStoreModel, "_kkv_identifier_location_unique", ("identifier", "location")),
    (MessageModel, "message_identifier_location_unique", ("identifier", "location")),
    (
        ProcessInstanceReportModel,
        "process_instance_report_unique",
        ("created_by_id", "identifier"),
    ),
    (
        ReferenceCacheModel,
        "reference_cache_uniq",
        ("generation_id", "identifier", "relative_location", "type"),
    ),
    (ServiceAccountModel, "service_account_uniq", ("name", "created_by_user_id")),
    (
        TaskDefinitionModel,
        "task_definition_unique",
        ("bpmn_process_definition_id", "bpmn_identifier"),
    ),
)

#: Upstream's global single-column UNIQUE, re-declared per tenant.  Pairs with
#: RELAXED_UNIQUES below, which removes the global one.
#: ``(model, constraint name, columns)``
ADDED_UNIQUES: tuple[tuple[type, str, tuple[str, ...]], ...] = (
    (
        BpmnProcessDefinitionModel,
        "bpmn_process_definition_full_process_model_hash_tenant_unique",
        (TENANT_COLUMN, "full_process_model_hash"),
    ),
    (
        MessageTriggerableProcessModel,
        "message_triggerable_process_model_message_name_tenant_unique",
        (TENANT_COLUMN, "message_name"),
    ),
    (
        PkceCodeVerifierModel,
        "pkce_code_verifier_pkce_id_tenant_unique",
        (TENANT_COLUMN, "pkce_id"),
    ),
    (RefreshTokenModel, "refresh_token_user_id_tenant_unique", (TENANT_COLUMN, "user_id")),
    (SecretModel, "secret_key_tenant_unique", (TENANT_COLUMN, "key")),
)

#: Upstream ``unique=True`` columns whose global uniqueness m8flow drops.  For the
#: models in ADDED_UNIQUES a per-tenant constraint takes over; ``user.username``
#: and ``permission_target.uri`` simply stop being unique, because the same person
#: and the same permission URI exist in more than one tenant.
#: ``(model, column)``
RELAXED_UNIQUES: tuple[tuple[type, str], ...] = (
    (BpmnProcessDefinitionModel, "full_process_model_hash"),
    (MessageTriggerableProcessModel, "message_name"),
    (PermissionTargetModel, "uri"),
    (PkceCodeVerifierModel, "pkce_id"),
    (RefreshTokenModel, "user_id"),
    (SecretModel, "key"),
    (UserModel, "username"),
)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def add_mapped_column(model: type, column: Column) -> None:
    """Add a column to a model that SQLAlchemy has already mapped.

    Two places need to learn about it and they are reached differently: the Table
    is what ``create_all()`` and Alembic autogenerate read, and ``append_column``
    covers that; the Mapper is what queries and instance attributes read, and a
    column appended after the class was mapped only reaches it via
    ``add_property``.
    """
    table: Table = model.__table__
    if column.name in table.c:
        return
    table.append_column(column)
    model.__mapper__.add_property(column.name, column)


def add_tenant_column(model: type) -> None:
    """Give a model the tenant column every tenant-scoped row is keyed by."""
    add_mapped_column(
        model,
        Column(TENANT_COLUMN, String(255), ForeignKey(TENANT_FK), nullable=False, index=True),
    )


def add_unique(model: type, name: str, column_names: tuple[str, ...]) -> None:
    table: Table = model.__table__
    if any(isinstance(c, UniqueConstraint) and c.name == name for c in table.constraints):
        return
    _require_columns(model, column_names)
    table.append_constraint(UniqueConstraint(*column_names, name=name))


def tenant_scope_unique(model: type, name: str, upstream_columns: tuple[str, ...]) -> None:
    """Widen an upstream UNIQUE so that it only applies within a tenant.

    The name is reused, so the constraint keeps matching what the migrations
    created.  Upstream's version is dropped by that name; if upstream declared it
    without one, fall back to matching on its columns.
    """
    if _discard_unique_named(model.__table__, name) is None:
        _discard_unique_over(model.__table__, upstream_columns)
    add_unique(model, name, (TENANT_COLUMN, *upstream_columns))


def relax_unique(model: type, column_name: str) -> None:
    """Drop a column's global uniqueness, keeping it indexed.

    Clearing ``Column.unique`` alone is not enough.  Upstream often declares
    ``index=True, unique=True``, which also builds an Index carrying its own
    ``unique`` flag - left alone, the uniqueness survives as a unique index and
    two tenants still cannot share a value.
    """
    table: Table = model.__table__
    _require_columns(model, (column_name,))
    table.c[column_name].unique = False
    _discard_unique_over(table, (column_name,))
    ensure_index(model, column_name)


def ensure_index(model: type, column_name: str) -> None:
    """Ensure a non-unique index over the column, relaxing one that is unique."""
    table: Table = model.__table__
    _require_columns(model, (column_name,))
    for index in table.indexes:
        if _index_columns(index) == (column_name,):
            index.unique = False
            return
    Index(f"ix_{table.name}_{column_name}", table.c[column_name])


def drop_index(model: type, column_name: str) -> None:
    """Remove a single-column index, for columns a composite constraint covers."""
    table: Table = model.__table__
    for index in list(table.indexes):
        if _index_columns(index) == (column_name,):
            table.indexes.discard(index)


def _index_columns(index: Index) -> tuple[str, ...]:
    return tuple(c.name for c in index.columns)


def _require_columns(model: type, column_names: tuple[str, ...]) -> None:
    """Fail loudly when upstream no longer has a column m8flow builds on.

    Silently skipping would leave the constraint - and the tenant isolation that
    depends on it - quietly missing.
    """
    missing = [name for name in column_names if name not in model.__table__.c]
    if missing:
        raise RuntimeError(
            f"upstream drift: {model.__name__}.{model.__table__.name} has no column(s) "
            f"{missing}. m8flow_backend.models.tenant_schema needs updating."
        )


def _discard_unique_named(table: Table, name: str) -> UniqueConstraint | None:
    for constraint in list(table.constraints):
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            table.constraints.discard(constraint)
            return constraint
    return None


def _discard_unique_over(table: Table, column_names: tuple[str, ...]) -> None:
    for constraint in list(table.constraints):
        if not isinstance(constraint, UniqueConstraint):
            continue
        if tuple(c.name for c in constraint.columns) == column_names:
            table.constraints.discard(constraint)


# ---------------------------------------------------------------------------
# Model extensions that are m8flow's alone
# ---------------------------------------------------------------------------


def _extend_process_instance() -> None:
    """Link a process instance to the BPMN version it was started from.

    ``process_model_bpmn_version`` is an m8flow table, so upstream has no reason
    to know about this column.
    """
    add_mapped_column(
        ProcessInstanceModel,
        Column(
            "bpmn_version_id",
            Integer,
            ForeignKey("process_model_bpmn_version.id"),
            nullable=True,
            index=True,
        ),
    )


def _extend_permission_target() -> None:
    """Let a permission target name the command it applies to.

    Upstream keys targets on ``uri`` alone; m8flow permits the same URI once per
    command, so uniqueness moves to the pair.  ``PermissionTargetModel.__init__``
    is taught to accept ``command`` by
    ``m8flow_backend.services.upstream_model_behaviour_patch``.
    """
    add_mapped_column(PermissionTargetModel, Column("command", String(255), nullable=True))
    add_unique(PermissionTargetModel, "permission_target_uri_command_unique", ("uri", "command"))
    ensure_index(PermissionTargetModel, "command")


def _extend_permission_assignment() -> None:
    """Re-declare upstream's uniqueness under the name m8flow's migrations use.

    The columns are unchanged.  Upstream's two single-column indexes go with it:
    m8flow's migrations never created them, and leaving them here would have
    autogenerate propose adding them to every database.
    """
    _discard_unique_named(PermissionAssignmentModel.__table__, "permission_assignment_uniq")
    add_unique(
        PermissionAssignmentModel,
        "permission_assignment_unique",
        ("principal_id", "permission_target_id", "permission"),
    )
    drop_index(PermissionAssignmentModel, "principal_id")
    drop_index(PermissionAssignmentModel, "permission_target_id")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_CONFIGURED = False


def configure() -> None:
    """Apply m8flow's delta to upstream's models.  Idempotent.

    Call once the models are imported.  Order matters within the function: the
    constraints below are declared over columns the first two steps add.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    for model in TENANT_SCOPED_MODELS:
        add_tenant_column(model)

    _extend_process_instance()
    _extend_permission_target()
    _extend_permission_assignment()

    for model, name, column_names in TENANT_SCOPED_UNIQUES:
        tenant_scope_unique(model, name, column_names)

    for model, name, column_names in ADDED_UNIQUES:
        add_unique(model, name, column_names)

    for model, column_name in RELAXED_UNIQUES:
        relax_unique(model, column_name)

    _assert_mapped()

    _CONFIGURED = True
    LOGGER.info("tenant_schema: configured %d tenant-scoped models", len(TENANT_SCOPED_MODELS))


def _assert_mapped() -> None:
    """Catch a tenant column that reached the Table but not the Mapper.

    Tenant scoping selects its entities by looking for ``m8f_tenant_id`` in
    ``mapper.columns``; a model missing there would silently query across every
    tenant.
    """
    unmapped = [
        model.__name__
        for model in TENANT_SCOPED_MODELS
        if TENANT_COLUMN not in model.__mapper__.columns
    ]
    if unmapped:
        raise RuntimeError(
            f"tenant_schema: {TENANT_COLUMN} is not mapped on {unmapped}. "
            "These models would not be tenant-scoped at query time."
        )
