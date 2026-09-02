from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from m8flow_backend.models.audit_mixin import AuditDateTimeMixin
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel, db


@dataclass
class NamedValueModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """The tenant-scoped catalog for manually managed configuration variables."""

    __tablename__ = "m8flow_named_value"
    __table_args__ = (
        db.CheckConstraint(
            "(is_sensitive = false AND value IS NOT NULL) OR "
            "(is_sensitive = true AND value IS NULL) OR "
            "(is_configured = false AND value IS NULL)",
            name="ck_m8flow_named_value_storage",
        ),
        db.UniqueConstraint(
            "m8f_tenant_id", "name", name="uq_m8flow_named_value_tenant_name"
        ),
        db.Index("ix_m8flow_named_value_tenant", "m8f_tenant_id"),
    )

    id: str = db.Column(db.String(36), primary_key=True, nullable=False)
    m8f_tenant_id: str = db.Column(
        db.String(255), db.ForeignKey("m8flow_tenant.id"), nullable=False, index=True
    )
    name: str = db.Column(db.String(255), nullable=False)
    description: str | None = db.Column(db.Text, nullable=True)
    is_sensitive: bool = db.Column(db.Boolean, nullable=False, default=False)
    # Sensitive values must bind as SQL NULL so the storage constraint can
    # distinguish them from the JSON literal ``null``.
    value: Any = db.Column(db.JSON(none_as_null=True), nullable=True)
    is_configured: bool = db.Column(db.Boolean, nullable=False, default=False)
    user_id: int | None = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.m8f_tenant_id,
            "name": self.name,
            "description": self.description,
            # Sensitive values are provider-backed and are never serialized.
            "value": None if self.is_sensitive else self.value,
            "isSensitive": self.is_sensitive,
            "isConfigured": self.is_configured,
            "userId": self.user_id,
            "createdAtInSeconds": self.created_at_in_seconds,
            "updatedAtInSeconds": self.updated_at_in_seconds,
        }
