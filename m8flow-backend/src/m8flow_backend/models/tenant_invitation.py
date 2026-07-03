from __future__ import annotations

import enum
from dataclasses import dataclass

from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db
from m8flow_backend.models.audit_mixin import AuditDateTimeMixin


class TenantInvitationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


@dataclass
class M8flowTenantInvitationModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """An invitation for a new user to join a tenant by setting a password.

    The raw invitation token is never persisted; only its SHA-256 hash is stored
    (``token_hash``). The Keycloak account is created lazily when the invitation is
    accepted, so a PENDING row implies no account exists yet.
    """

    __tablename__ = "m8flow_tenant_invitation"

    id: str = db.Column(db.String(255), primary_key=True)
    m8f_tenant_id: str = db.Column(
        db.String(255),
        db.ForeignKey("m8flow_tenant.id"),
        nullable=False,
        index=True,
    )
    email: str = db.Column(db.String(255), nullable=False, index=True)
    # Comma-separated tenant role names (e.g. "tenant-admin,editor").
    roles: str = db.Column(db.String(1024), nullable=False)
    token_hash: str = db.Column(db.String(255), nullable=False, unique=True, index=True)
    status: TenantInvitationStatus = db.Column(
        db.Enum(TenantInvitationStatus),
        default=TenantInvitationStatus.PENDING,
        nullable=False,
    )
    expires_at_in_seconds: int = db.Column(db.Integer, nullable=False)
    accepted_at_in_seconds: int | None = db.Column(db.Integer, nullable=True)
    created_by: str = db.Column(db.String(255), nullable=False)
    modified_by: str = db.Column(db.String(255), nullable=False)

    def role_names(self) -> list[str]:
        return [role.strip() for role in (self.roles or "").split(",") if role.strip()]

    def __repr__(self) -> str:
        return (
            f"<M8flowTenantInvitationModel(id={self.id}, "
            f"tenant_id={self.m8f_tenant_id}, email={self.email}, status={self.status})>"
        )
