"""m8flow's additions really did land on upstream's models.

configure() has already run by the time these execute - tests/conftest.py boots
the patch registry in pytest_configure.
"""
from __future__ import annotations

import pytest
from sqlalchemy import UniqueConstraint

from m8flow_backend.models import tenant_schema
from m8flow_backend.models.tenant_schema import TENANT_COLUMN
from spiffworkflow_backend.models.permission_assignment import PermissionAssignmentModel
from spiffworkflow_backend.models.permission_target import PermissionTargetModel
from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
from spiffworkflow_backend.models.user import UserModel


def _unique_constraints(model: type) -> dict[str, tuple[str, ...]]:
    return {
        constraint.name: tuple(c.name for c in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


@pytest.mark.parametrize("model", tenant_schema.TENANT_SCOPED_MODELS, ids=lambda m: m.__name__)
def test_tenant_column_reaches_both_the_table_and_the_mapper(model: type) -> None:
    # The table is what the migrations are compared against; the mapper is what
    # tenant scoping filters on. A column can reach one without the other.
    assert TENANT_COLUMN in model.__table__.c
    assert TENANT_COLUMN in model.__mapper__.columns

    column = model.__table__.c[TENANT_COLUMN]
    assert column.nullable is False
    assert {fk.target_fullname for fk in column.foreign_keys} == {tenant_schema.TENANT_FK}


@pytest.mark.parametrize(
    "model", (UserModel, PermissionTargetModel, PermissionAssignmentModel), ids=lambda m: m.__name__
)
def test_shared_models_stay_untenanted(model: type) -> None:
    # Users and permissions are shared across tenants by design.
    assert TENANT_COLUMN not in model.__table__.c


def test_m8flow_only_columns_are_mapped() -> None:
    assert "bpmn_version_id" in ProcessInstanceModel.__mapper__.columns
    assert "command" in PermissionTargetModel.__mapper__.columns


@pytest.mark.parametrize(
    ("model", "column_name"), tenant_schema.RELAXED_UNIQUES, ids=lambda arg: getattr(arg, "__name__", arg)
)
def test_upstream_global_uniqueness_is_gone(model: type, column_name: str) -> None:
    # Left in place, any of these would stop a second tenant from reusing a
    # username, a secret key or a process hash.
    assert not model.__table__.c[column_name].unique
    assert (column_name,) not in _unique_constraints(model).values()
    for index in model.__table__.indexes:
        if tuple(c.name for c in index.columns) == (column_name,):
            assert not index.unique


@pytest.mark.parametrize(
    ("model", "name", "upstream_columns"),
    tenant_schema.TENANT_SCOPED_UNIQUES,
    ids=lambda arg: getattr(arg, "__name__", arg),
)
def test_upstream_composite_uniques_are_scoped_to_a_tenant(
    model: type, name: str, upstream_columns: tuple[str, ...]
) -> None:
    assert _unique_constraints(model)[name] == (TENANT_COLUMN, *upstream_columns)


@pytest.mark.parametrize(
    ("model", "name", "column_names"), tenant_schema.ADDED_UNIQUES, ids=lambda arg: getattr(arg, "__name__", arg)
)
def test_per_tenant_uniques_replace_the_global_ones(
    model: type, name: str, column_names: tuple[str, ...]
) -> None:
    assert _unique_constraints(model)[name] == column_names


def test_configure_is_idempotent() -> None:
    before = len(ProcessInstanceModel.__table__.c)
    tenant_schema.configure()
    assert len(ProcessInstanceModel.__table__.c) == before
