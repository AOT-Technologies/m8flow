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
    # Terminal-until-reconfigured: the tenant has no usable NATS_SMTP_* secrets, so no
    # amount of retrying can deliver the email. Deliberately absent from
    # ExternalFormNotificationService.CLAIMABLE_STATUSES — that tuple is the only
    # predicate the sweep uses, so parking a row here stops the retry loop dead — and
    # from ACTIONABLE_STATUSES, since the link was never delivered to anyone.
    # Rows leave this state via revive_smtp_unconfigured() (auto, once the tenant's
    # SMTP secrets appear) or an admin resend.
    smtp_unconfigured = "smtp_unconfigured"


# Statuses for which the secure link may still be used to submit the form.
# "failed" means a notification/resume attempt failed; the link itself stays usable,
# because it was already delivered at least once.
#
# "smtp_unconfigured" is deliberately absent. Such a request was never emailed, so nobody
# can legitimately hold its link — the only way to obtain one is to read reference_id out
# of the database. Accepting it would let an operator submit a form as the recipient. Once
# SMTP is configured, revive_smtp_unconfigured() returns the row to "pending" and the link
# becomes usable in the normal way.
ACTIONABLE_STATUSES = (
    ExternalFormRequestStatus.pending.value,
    ExternalFormRequestStatus.notified.value,
    ExternalFormRequestStatus.failed.value,
)

# Statuses in which the request is still open — not submitted, completed, superseded, or
# expired. Broader than ACTIONABLE_STATUSES: a parked request is not submittable, but it is
# still the live request for its (task, recipient) pair, so it must suppress duplicate row
# creation, still be expired by TTL, and still be superseded when a sibling submits.
OPEN_STATUSES = ACTIONABLE_STATUSES + (ExternalFormRequestStatus.smtp_unconfigured.value,)

# Column width of last_error. Writers must truncate to this; an SMTP exception message
# (or a provider's multi-line rejection) can easily exceed it.
LAST_ERROR_MAX_LENGTH = 500


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
    # Why the last delivery attempt failed, so an admin can diagnose from the UI instead
    # of the worker logs. Bounded and truncated on write; never holds secret values.
    last_error: Optional[str] = db.Column(db.String(LAST_ERROR_MAX_LENGTH), nullable=True)

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

    def to_admin_dict(self) -> dict[str, Any]:
        """Shape returned to tenant admins in the notification-status list.

        Deliberately omits reference_id: it is the bearer credential in the emailed
        secure link (external_form_show/submit authenticate on it alone), so it must not
        be readable by anyone other than its recipient. Admin actions key on `id`."""
        return {
            "id": self.id,
            "process_instance_id": self.process_instance_id,
            "task_guid": self.task_guid,
            "email": self.email,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "created_at_in_seconds": self.created_at_in_seconds,
            "updated_at_in_seconds": self.updated_at_in_seconds,
            "notified_at_in_seconds": self.notified_at_in_seconds,
            "expires_at_in_seconds": self.expires_at_in_seconds,
        }

    def __repr__(self) -> str:
        return (
            f"<ExternalFormRequestModel(reference_id={self.reference_id},"
            f" process_instance_id={self.process_instance_id}, task_guid={self.task_guid},"
            f" status={self.status})>"
        )
