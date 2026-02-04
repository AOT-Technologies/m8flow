# extensions/m8flow-backend/src/m8flow_backend/models/audit_mixin.py
from __future__ import annotations

from spiffworkflow_backend.models.db import db


class AuditDateTimeMixin:  # pylint: disable=too-few-public-methods
    """Spiff-standard audit timestamps stored as epoch seconds.

    Any model inheriting this mixin and `SpiffworkflowBaseDBModel` will have these fields
    automatically set/updated by Spiff's SQLAlchemy listeners (see `spiffworkflow_backend.models.db`).
    """

    created_at_in_seconds = db.Column(db.Integer, nullable=False)
    updated_at_in_seconds = db.Column(db.Integer, nullable=False)

    # Alias properties used in some m8flow code paths.
    @property
    def created(self) -> int:
        return self.created_at_in_seconds

    @property
    def modified(self) -> int:
        return self.updated_at_in_seconds
