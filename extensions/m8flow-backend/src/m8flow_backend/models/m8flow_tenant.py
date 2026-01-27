from __future__ import annotations

import enum
from dataclasses import dataclass

from sqlalchemy import func
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db
from m8flow_backend.models.audit_mixin import AuditDateTimeMixin


class TenantStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DELETED = "DELETED"


@dataclass
class M8flowTenantModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """SQLAlchemy model for M8flowTenantModel."""
    __tablename__ = "m8flow_tenant"

    id: str = db.Column(db.String(255), primary_key=True)
    name: str = db.Column(db.String(255), nullable=False)
    slug: str = db.Column(db.String(255), unique=True, index=True, nullable=False)
    status: TenantStatus = db.Column(
        db.Enum(TenantStatus), default=TenantStatus.ACTIVE, nullable=False
    )
    created_by: str | None = db.Column(db.String(255), nullable=False)
    modified_by: str | None = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<M8flowTenantModel(name={self.name}, slug={self.slug}, status={self.status})>"
