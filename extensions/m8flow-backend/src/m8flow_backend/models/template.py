from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship, validates

from spiffworkflow_backend.helpers.spiff_enum import SpiffEnum
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db
from m8flow_backend.models.audit_mixin import AuditDateTimeMixin


class TemplateVisibility(SpiffEnum):
    private = "PRIVATE"
    tenant = "TENANT"
    public = "PUBLIC"


@dataclass
class TemplateModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """Template metadata and version rows (one row per version)."""

    __tablename__ = "m8flow_templates"
    __table_args__ = (
        UniqueConstraint("m8f_tenant_id", "template_key", "version", name="uq_template_key_version_tenant"),
        Index("ix_template_template_key", "template_key"),
        Index("ix_template_m8f_tenant_id", "m8f_tenant_id"),
        Index("ix_template_visibility", "visibility"),
        Index("ix_template_is_published", "is_published"),
        Index("ix_template_status", "status"),
    )
    __allow_unmapped__ = True

    id: int = db.Column(db.Integer, primary_key=True)
    template_key: str = db.Column(db.String(255), nullable=False)
    version: str = db.Column(db.String(50), nullable=False)
    name: str = db.Column(db.String(255), nullable=False)
    description: Optional[str] = db.Column(db.Text, nullable=True)
    tags: list[str] | None = db.Column(db.JSON, nullable=True)
    category: Optional[str] = db.Column(db.String(255), nullable=True)
    m8f_tenant_id: str = db.Column(
        db.String(255),
        db.ForeignKey("m8flow_tenant.id"),
        nullable=False,
    )  # type: ignore
    visibility: str = db.Column(db.String(20), nullable=False, default=TemplateVisibility.private.value)
    files: list[dict] = db.Column(db.JSON, nullable=False)  # [{"file_type": "bpmn"|"json"|"dmn"|"md", "file_name": str}]
    is_published: bool = db.Column(db.Boolean, default=False, nullable=False)
    status: Optional[str] = db.Column(db.String(50), nullable=True)
    is_deleted: bool = db.Column(db.Boolean, default=False, nullable=False)

    created_by: str = db.Column(db.String(255), nullable=False)
    modified_by: str = db.Column(db.String(255), nullable=False)

    @validates("visibility")
    def validate_visibility(self, _key: str, value: str) -> str:
        # First try to find by member name (for backward compatibility)
        try:
            m_type = getattr(TemplateVisibility, value, None)
            if m_type is not None:
                return m_type.value
        except Exception:
            pass
        
        # If not found by name, try to find by value
        for member in TemplateVisibility:
            if member.value == value:
                return member.value
        
        # If neither found, raise error
        raise ValueError(f"{self.__class__.__name__}: invalid visibility: {value}")

    def is_private(self) -> bool:
        return self.visibility == TemplateVisibility.private.value

    def is_tenant_visible(self) -> bool:
        return self.visibility == TemplateVisibility.tenant.value

    def is_public(self) -> bool:
        return self.visibility == TemplateVisibility.public.value