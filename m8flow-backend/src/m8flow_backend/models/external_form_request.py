from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Optional

from spiffworkflow_backend.helpers.spiff_enum import SpiffEnum
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db

from m8flow_backend.models.audit_mixin import AuditDateTimeMixin
from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped


class ExternalFormRequestStatus(SpiffEnum):
    pending = "pending"
    notified = "notified"
    submitted = "submitted"
    completed = "completed"
    failed = "failed"
    expired = "expired"
    superseded = "superseded"


# Statuses for which the secure link may still be used to submit the form.
# "failed" means a notification/resume attempt failed; the link itself stays usable.
ACTIONABLE_STATUSES = (
    ExternalFormRequestStatus.pending.value,
    ExternalFormRequestStatus.notified.value,
    ExternalFormRequestStatus.failed.value,
)


@dataclass
class ExternalFormRequestModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """One external-form request per (human task, recipient); reference_id is the
    unguessable token in the emailed secure link."""

    __tablename__ = "m8flow_external_form_requests"
    __table_args__ = (
        db.Index("ix_m8flow_external_form_requests_instance_task", "process_instance_id", "task_guid"),
        db.Index("ix_m8flow_external_form_requests_sweep", "status", "notified_at_in_seconds"),
    )

    id: int = db.Column(db.Integer, primary_key=True)
    reference_id: str = db.Column(db.String(255), nullable=False, unique=True, index=True)
    process_instance_id: int = db.Column(db.Integer, nullable=False)
    task_guid: str = db.Column(db.String(36), nullable=False)
    recipient_user_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    email: str = db.Column(db.String(255), nullable=False)
    user_details: Optional[dict] = db.Column(db.JSON, nullable=True)
    # Text (not a bounded varchar): the configured external form URL can embed an entire
    # form schema (e.g. the M8F Forms app lz-compresses the Form.io schema into ?form=...),
    # which routinely exceeds a few KB. A fixed varchar truncates the insert and breaks
    # notification creation. See migration m5e6f7a8b1c2.
    external_form_url: str = db.Column(db.Text, nullable=False)
    status: str = db.Column(
        db.String(32), nullable=False, default=ExternalFormRequestStatus.pending.value, index=True
    )
    form_submission_data: Optional[dict] = db.Column(db.JSON, nullable=True)
    expires_at_in_seconds: Optional[int] = db.Column(db.Integer, nullable=True)
    attempts: int = db.Column(db.Integer, nullable=False, default=0)
    notified_at_in_seconds: Optional[int] = db.Column(db.Integer, nullable=True)

    def is_actionable(self) -> bool:
        return self.status in ACTIONABLE_STATUSES

    def to_public_dict(self) -> dict[str, Any]:
        """Shape returned to the external mini-app. No recipient PII."""
        return {
            "reference_id": self.reference_id,
            "status": self.status,
            "external_form_url": self.external_form_url,
            "process_instance_id": self.process_instance_id,
        }

    def __repr__(self) -> str:
        return (
            f"<ExternalFormRequestModel(reference_id={self.reference_id},"
            f" process_instance_id={self.process_instance_id}, task_guid={self.task_guid},"
            f" status={self.status})>"
        )
