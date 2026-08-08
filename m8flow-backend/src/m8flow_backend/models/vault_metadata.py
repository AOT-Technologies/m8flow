from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import ForeignKey

from m8flow_backend.models.audit_mixin import AuditDateTimeMixin
from m8flow_backend.models.tenant_scoped import M8fTenantScopedMixin, TenantScoped
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel, db
from spiffworkflow_backend.models.user import UserModel


@dataclass(repr=False)
class VaultMetadataModel(M8fTenantScopedMixin, TenantScoped, SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """Metadata for secrets whose values live only in Vault."""

    __tablename__ = "vault_metadata"
    __table_args__ = (
        db.UniqueConstraint("m8f_tenant_id", "name", name="uq_vault_metadata_tenant_name"),
        db.Index("ix_vault_metadata_tenant_name", "m8f_tenant_id", "name"),
    )

    id: str = db.Column(db.String(64), primary_key=True, nullable=False)
    name: str = db.Column(db.String(255), nullable=False)
    user_id: int = db.Column(ForeignKey(UserModel.id), nullable=False, index=True)  # type: ignore
    created_by: str = db.Column(db.String(255), nullable=False)
    modified_by: str = db.Column(db.String(255), nullable=False)

    @property
    def key(self) -> str:
        """Compatibility alias for the upstream secret API contract."""
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.name,
            "user_id": self.user_id,
            "updated_at_in_seconds": self.updated_at_in_seconds,
            "created_at_in_seconds": self.created_at_in_seconds,
        }

    def __repr__(self) -> str:
        return f"<VaultMetadataModel(id={self.id}, tenant_id={self.m8f_tenant_id}, name={self.name})>"
