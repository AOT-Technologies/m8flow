from __future__ import annotations
from dataclasses import dataclass
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel, db
from m8flow_backend.models.audit_mixin import AuditDateTimeMixin
from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped

@dataclass
class NatsTokenModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """SQLAlchemy model for NATS tokens."""
    __tablename__ = "m8flow_nats_tokens"

    m8f_tenant_id: str = db.Column(
        db.String(255),
        db.ForeignKey("m8flow_tenant.id"),
        primary_key=True
    )
    token: str = db.Column(db.String(255), nullable=False, unique=True)
    created_by: str = db.Column(db.String(255), nullable=False)
    modified_by: str = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<NatsTokenModel(tenant_id={self.m8f_tenant_id}, token={self.token})>"
