from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import validates

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.permission_target import PermissionTargetModel
from spiffworkflow_backend.models.principal import PrincipalModel


class PermitDeny(enum.Enum):
    permit = "permit"
    deny = "deny"


class Permission(enum.Enum):
    create = "create"
    delete = "delete"
    read = "read"
    update = "update"


class PermissionAssignmentModel(SpiffworkflowBaseDBModel):
    __tablename__ = "permission_assignment"
    __table_args__ = (
        db.UniqueConstraint(
            "principal_id",
            "permission_target_id",
            "permission",
            name="permission_assignment_unique",
        ),
        db.Index("ix_permission_assignment_principal_id", "principal_id"),
        db.Index("ix_permission_assignment_permission_target_id", "permission_target_id"),
        {"extend_existing": True},
    )

    id = db.Column(db.Integer, primary_key=True)
    principal_id = db.Column(ForeignKey(PrincipalModel.id), nullable=False)
    permission_target_id = db.Column(ForeignKey(PermissionTargetModel.id), nullable=False)  # type: ignore[arg-type]
    permission_target = db.relationship(PermissionTargetModel, backref="permission_assignments")
    grant_type = db.Column(db.String(50), nullable=False)
    permission = db.Column(db.String(50), nullable=False)

    @validates("grant_type")
    def validate_grant_type(self, key: str, value: str) -> Any:
        return self.validate_enum_field(key, value, PermitDeny)

    @validates("permission")
    def validate_permission(self, key: str, value: str) -> Any:
        return self.validate_enum_field(key, value, Permission)

    def __repr__(self) -> str:
        value = (
            f"PermissionAssignmentModel(id={self.id}, target={self.permission_target.uri}, "
            f"permission={self.permission}, grant_type={self.grant_type})"
        )
        return value


def _deduplicate_table_indexes_and_constraints() -> None:
    table = PermissionAssignmentModel.__table__

    seen_indexes: set[tuple[str | None, tuple[str, ...]]] = set()
    for index in list(table.indexes):
        key = (index.name, tuple(column.name for column in index.columns))
        if key in seen_indexes:
            table.indexes.discard(index)
            continue
        seen_indexes.add(key)

    seen_uniques: set[tuple[str | None, tuple[str, ...]]] = set()
    for constraint in list(table.constraints):
        if not isinstance(constraint, UniqueConstraint):
            continue
        key = (constraint.name, tuple(column.name for column in constraint.columns))
        if key in seen_uniques:
            table.constraints.discard(constraint)
            continue
        seen_uniques.add(key)


_deduplicate_table_indexes_and_constraints()
