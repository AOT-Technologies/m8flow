from __future__ import annotations

import enum
import time
from typing import Any

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase


class ExternalFormRequestStatus(str, enum.Enum):
    pending = "pending"
    notified = "notified"
    submitted = "submitted"
    completed = "completed"
    failed = "failed"
    expired = "expired"
    # A recipient's link is superseded once a sibling recipient's submission
    # completes the same task -- see ExternalFormService._supersede_siblings.
    superseded = "superseded"
    # Terminal-until-reconfigured: the tenant has no usable NATS_SMTP_* secrets, so no
    # amount of retrying can deliver the email. Deliberately absent from
    # ExternalFormNotificationService.CLAIMABLE_STATUSES -- that tuple is the only
    # predicate the sweep uses, so parking a row here stops the retry loop dead -- and
    # from ACTIONABLE_STATUSES, since the link was never delivered to anyone.
    # Rows leave this state via revive_smtp_unconfigured() (auto, once the tenant's
    # SMTP secrets appear) or an admin resend.
    smtp_unconfigured = "smtp_unconfigured"


# Statuses for which the secure link may still be used to submit the form.
# "failed" means a notification/resume attempt failed; the link itself stays usable,
# because it was already delivered at least once.
#
# "smtp_unconfigured" is deliberately absent. Such a request was never emailed, so nobody
# can legitimately hold its link -- the only way to obtain one is to read reference_id out
# of the database. Accepting it would let an operator submit a form as the recipient. Once
# SMTP is configured, revive_smtp_unconfigured() returns the row to "pending" and the link
# becomes usable in the normal way.
ACTIONABLE_STATUSES = (
    ExternalFormRequestStatus.pending.value,
    ExternalFormRequestStatus.notified.value,
    ExternalFormRequestStatus.failed.value,
)

# Statuses in which the request is still open -- not submitted, completed, superseded, or
# expired. Broader than ACTIONABLE_STATUSES: a parked request is not submittable, but it is
# still the live request for its (task, recipient) pair, so it must suppress duplicate row
# creation, still be expired by TTL, and still be superseded when a sibling submits.
OPEN_STATUSES = ACTIONABLE_STATUSES + (ExternalFormRequestStatus.smtp_unconfigured.value,)

# Column width of last_error. Writers must truncate to this; an SMTP exception message
# (or a provider's multi-line rejection) can easily exceed it.
LAST_ERROR_MAX_LENGTH = 500


def truncate_last_error(message: Any) -> str | None:
    """Fit a failure reason into last_error. SMTP rejections are routinely longer than
    the column, and an oversized value would fail the write on strict backends."""
    text = str(message or "").strip()
    if not text:
        return None
    return text[:LAST_ERROR_MAX_LENGTH]


class ExternalFormRequestModel(HostBase):
    """Tracks one external (unauthenticated, link-based) form request per
    recipient of a human task.

    Created from the live ORM metadata by the root migration
    (1518b05122bc_create_m8flow_tables.py); later column additions have their own
    incremental revision -- keep the two in sync."""

    __tablename__ = "m8flow_external_form_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reference_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    process_instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_guid: Mapped[str] = mapped_column(String(36), nullable=False)
    recipient_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    user_details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    external_form_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    form_submission_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    expires_at_in_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notified_at_in_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Why the last delivery attempt failed, so an admin can diagnose from the API instead
    # of the worker logs. Bounded and truncated on write; never holds secret values.
    last_error: Mapped[str | None] = mapped_column(String(LAST_ERROR_MAX_LENGTH), nullable=True)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=lambda: int(time.time()))
    updated_at_in_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=lambda: int(time.time()), onupdate=lambda: int(time.time())
    )

    def is_actionable(self) -> bool:
        return self.status in ACTIONABLE_STATUSES

    def to_public_dict(self) -> dict[str, Any]:
        """Fields safe to hand to the unauthenticated external mini-app --
        deliberately excludes form_submission_data, user_details, and attempts."""
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


__all__ = [
    "ExternalFormRequestModel",
    "ExternalFormRequestStatus",
    "ACTIONABLE_STATUSES",
    "OPEN_STATUSES",
    "LAST_ERROR_MAX_LENGTH",
    "truncate_last_error",
]
