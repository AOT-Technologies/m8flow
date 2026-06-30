from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import validates

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db


class InvalidPermissionTargetUriError(Exception):
    pass


@dataclass
class PermissionTargetModel(SpiffworkflowBaseDBModel):
    URI_ALL = "/%"

    __tablename__ = "permission_target"
    __table_args__ = (
        db.UniqueConstraint("uri", "command", name="permission_target_uri_command_unique"),
        db.Index("ix_permission_target_uri", "uri"),
        db.Index("ix_permission_target_command", "command"),
        {"extend_existing": True},
    )

    id: int = db.Column(db.Integer, primary_key=True)
    uri: str = db.Column(db.String(255), nullable=False)
    command: str | None = db.Column(db.String(255), nullable=True)

    def __init__(self, uri: str, command: str | None = None, id: int | None = None):
        if id:
            self.id = id
        uri_with_percent = re.sub(r"\*", "%", uri)
        self.uri = uri_with_percent
        self.command = command.strip() or None if isinstance(command, str) else None

    @validates("uri")
    def validate_uri(self, key: str, value: str) -> str:
        if re.search(r"%.", value):
            raise InvalidPermissionTargetUriError(f"Wildcard must appear at end: {value}")
        return value


def _remove_legacy_uri_unique_constraint() -> None:
    table = PermissionTargetModel.__table__
    for constraint in list(table.constraints):
        if not isinstance(constraint, UniqueConstraint):
            continue
        if [column.name for column in constraint.columns] != ["uri"]:
            continue
        table.constraints.discard(constraint)


_remove_legacy_uri_unique_constraint()
