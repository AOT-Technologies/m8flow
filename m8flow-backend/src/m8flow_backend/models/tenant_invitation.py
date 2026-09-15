from __future__ import annotations

import enum
import time

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase


class TenantInvitationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class M8flowTenantInvitationModel(HostBase):
    """Schema matches migrations/versions/k3c4d5e6f7g8_add_tenant_invitation.py
    -- keep the two in sync. (models/native.py's prior definition of this
    class -- id: int, token, tenant_id, role, no status/expiry/audit columns
    at all -- targeted none of these real columns; see architecture review
    finding S2's discovery note.)"""

    __tablename__ = "m8flow_tenant_invitation"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    roles: Mapped[str] = mapped_column(String(1024), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    status: Mapped[TenantInvitationStatus] = mapped_column(
        SAEnum(TenantInvitationStatus, name="tenantinvitationstatus"),
        nullable=False,
        default=TenantInvitationStatus.PENDING,
    )
    expires_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_at_in_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    modified_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=lambda: int(time.time()))
    updated_at_in_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=lambda: int(time.time()), onupdate=lambda: int(time.time())
    )

    def role_names(self) -> list[str]:
        return [name for name in (self.roles or "").split(",") if name]


__all__ = ["M8flowTenantInvitationModel", "TenantInvitationStatus"]
