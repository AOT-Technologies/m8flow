"""Model for tracking soft-deleted process models."""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import Index

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db
from m8flow_backend.models.audit_mixin import AuditDateTimeMixin
from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped


class DeletionStatus(str, enum.Enum):
    SOFT_DELETED = "SOFT_DELETED"
    RESTORED = "RESTORED"
    PURGED = "PURGED"


@dataclass
class ProcessModelDeletionModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """Tracks soft-deleted process models for restore and purge lifecycle."""

    __tablename__ = "m8flow_process_model_deletion"
    __table_args__ = (
        Index("ix_pmd_m8f_tenant_id", "m8f_tenant_id"),
        Index("ix_pmd_original_identifier", "original_identifier"),
        Index("ix_pmd_status", "status"),
        Index("ix_pmd_deleted_at", "deleted_at_in_seconds"),
    )
    __allow_unmapped__ = True

    id: int = db.Column(db.Integer, primary_key=True)
    original_identifier: str = db.Column(db.String(255), nullable=False)
    deleted_identifier: str = db.Column(db.String(255), nullable=False)
    display_name: str = db.Column(db.String(255), nullable=False)
    parent_group_id: Optional[str] = db.Column(db.String(255), nullable=True)
    status: str = db.Column(db.String(20), nullable=False, default=DeletionStatus.SOFT_DELETED.value)
    deleted_at_in_seconds: int = db.Column(db.Integer, nullable=False)
    deleted_by: str = db.Column(db.String(255), nullable=False)
    restored_at_in_seconds: Optional[int] = db.Column(db.Integer, nullable=True)
    restored_by: Optional[str] = db.Column(db.String(255), nullable=True)
    restored_identifier: Optional[str] = db.Column(db.String(255), nullable=True)
    purged_at_in_seconds: Optional[int] = db.Column(db.Integer, nullable=True)
    notes: Optional[dict] = db.Column(db.JSON, nullable=True)

    def serialized(self) -> dict:
        return {
            "id": self.id,
            "m8f_tenant_id": self.m8f_tenant_id,
            "original_identifier": self.original_identifier,
            "deleted_identifier": self.deleted_identifier,
            "display_name": self.display_name,
            "parent_group_id": self.parent_group_id,
            "status": self.status,
            "deleted_at_in_seconds": self.deleted_at_in_seconds,
            "deleted_by": self.deleted_by,
            "restored_at_in_seconds": self.restored_at_in_seconds,
            "restored_by": self.restored_by,
            "restored_identifier": self.restored_identifier,
            "purged_at_in_seconds": self.purged_at_in_seconds,
            "notes": self.notes,
            "created_at_in_seconds": self.created_at_in_seconds,
            "updated_at_in_seconds": self.updated_at_in_seconds,
        }
