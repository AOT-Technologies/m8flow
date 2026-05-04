from __future__ import annotations
from dataclasses import dataclass
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel, db
from m8flow_backend.models.audit_mixin import AuditDateTimeMixin

@dataclass
class NatsTokenModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """SQLAlchemy model for NATS tokens."""
    __tablename__ = "m8flow_nats_tokens"

    m8f_tenant_id: str = db.Column(
        db.String(255),
        db.ForeignKey("m8flow_tenant.id"),
        primary_key=True,
        nullable=False,
        index=True
    )
    token: str = db.Column(db.String(255), nullable=False, unique=True)
    created_by: str = db.Column(db.String(255), nullable=False)
    modified_by: str = db.Column(db.String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<NatsTokenModel(tenant_id={self.m8f_tenant_id})>"
