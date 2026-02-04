# extensions/m8flow-backend/src/m8flow_backend/models/audit_mixin.py
from __future__ import annotations

import datetime

from spiffworkflow_backend.models.db import db


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class AuditDateTimeMixin:  # pylint: disable=too-few-public-methods
    """Inherit this class to extend the model with created and modified column."""

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    modified_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    # Backwards-compat aliases for some .created/.modified previous usages:
    @property
    def created(self):
        return self.created_at

    @property
    def modified(self):
        return self.modified_at
