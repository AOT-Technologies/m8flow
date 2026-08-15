from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from m8flow_backend.models.audit_mixin import AuditDateTimeMixin
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel, db


@dataclass
class AuditLogModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """Generic application audit/event record.

    This table is intentionally broader than Vault so it can hold future audit
    categories without another schema redesign.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        db.Index("ix_audit_log_category_created_at", "category", "created_at_in_seconds"),
        db.Index("ix_audit_log_tenant_created_at", "m8f_tenant_id", "created_at_in_seconds"),
    )

    id: str = db.Column(db.String(64), primary_key=True, nullable=False)
    category: str = db.Column(db.String(64), nullable=False, index=True)
    event_type: str = db.Column(db.String(255), nullable=False, index=True)
    source: str = db.Column(db.String(255), nullable=False)
    status: str = db.Column(db.String(32), nullable=False, index=True)
    severity: str = db.Column(db.String(32), nullable=False, default="info")
    message: str | None = db.Column(db.Text, nullable=True)

    # Keep tenant and actor references soft so audit retention is not coupled to
    # lifecycle changes in the referenced domain records.
    m8f_tenant_id: str | None = db.Column(db.String(255), nullable=True, index=True)
    actor_type: str | None = db.Column(db.String(64), nullable=True)
    actor_id: str | None = db.Column(db.String(255), nullable=True)
    actor_username: str | None = db.Column(db.String(255), nullable=True)

    resource_type: str | None = db.Column(db.String(64), nullable=True)
    resource_id: str | None = db.Column(db.String(255), nullable=True)
    resource_name: str | None = db.Column(db.String(255), nullable=True)

    request_id: str | None = db.Column(db.String(255), nullable=True, index=True)
    correlation_id: str | None = db.Column(db.String(255), nullable=True, index=True)
    details: dict[str, Any] | None = db.Column(db.JSON, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditLogModel(id={self.id}, category={self.category}, event_type={self.event_type}, "
            f"status={self.status}, tenant_id={self.m8f_tenant_id})>"
        )
