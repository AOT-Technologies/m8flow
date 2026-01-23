import datetime
from spiffworkflow_backend.models.db import db

def iso_utcnow():
    """Return the current UTC datetime in ISO format with timezone awareness."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class AuditDateTimeMixin:  # pylint: disable=too-few-public-methods
    """Inherit this class to extend the model with created and modified column."""

    created = db.Column("created_at", db.DateTime(timezone=True), nullable=False, default=iso_utcnow)
    modified = db.Column(
        "modified_at",
        db.DateTime(timezone=True),
        default=iso_utcnow,
        onupdate=iso_utcnow,
    )
