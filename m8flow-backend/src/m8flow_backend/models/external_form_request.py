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


ACTIONABLE_STATUSES = {
    ExternalFormRequestStatus.pending.value,
    ExternalFormRequestStatus.notified.value,
}


class ExternalFormRequestModel(HostBase):
    """Tracks one external (unauthenticated, link-based) form request per
    recipient of a human task. Schema matches migrations/versions/
    k3c4d5e6f7a9_add_external_form_requests_table.py -- keep the two in sync."""

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


__all__ = ["ExternalFormRequestModel", "ExternalFormRequestStatus", "ACTIONABLE_STATUSES"]
