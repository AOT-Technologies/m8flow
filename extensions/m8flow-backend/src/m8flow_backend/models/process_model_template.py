"""Model for tracking which template a process model was created from."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import relationship

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db
from m8flow_backend.models.audit_mixin import AuditDateTimeMixin
from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped


@dataclass
class ProcessModelTemplateModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """Tracks which template a process model was created from.
    
    This model stores the provenance information linking a process model
    to the template (and specific version) it was created from.
    """

    __tablename__ = "m8flow_process_model_template"
    __table_args__ = (
        Index("ix_pmt_process_model_identifier", "process_model_identifier"),
        Index("ix_pmt_source_template_id", "source_template_id"),
        Index("ix_pmt_source_template_key", "source_template_key"),
        Index("ix_pmt_m8f_tenant_id", "m8f_tenant_id"),
    )
    __allow_unmapped__ = True

    id: int = db.Column(db.Integer, primary_key=True)
    
    # The process model identifier (e.g., "my-group/my-model")
    process_model_identifier: str = db.Column(db.String(255), nullable=False, unique=True)
    
    # Reference to the source template
    source_template_id: int = db.Column(
        db.Integer,
        db.ForeignKey("m8flow_templates.id"),
        nullable=False,
    )
    
    # Denormalized template info for quick access and historical record
    # (in case the template is deleted or modified)
    source_template_key: str = db.Column(db.String(255), nullable=False)
    source_template_version: str = db.Column(db.String(50), nullable=False)
    source_template_name: str = db.Column(db.String(255), nullable=False)
    
    # Who created this process model from the template
    created_by: str = db.Column(db.String(255), nullable=False)
    
    # Relationship to the template
    source_template = relationship(
        "TemplateModel",
        foreign_keys=[source_template_id],
        lazy="joined",
    )

    def serialized(self) -> dict:
        """Return object data in serializable format."""
        return {
            "id": self.id,
            "process_model_identifier": self.process_model_identifier,
            "source_template_id": self.source_template_id,
            "source_template_key": self.source_template_key,
            "source_template_version": self.source_template_version,
            "source_template_name": self.source_template_name,
            "m8f_tenant_id": self.m8f_tenant_id,
            "created_by": self.created_by,
            "created_at_in_seconds": self.created_at_in_seconds,
            "updated_at_in_seconds": self.updated_at_in_seconds,
        }
