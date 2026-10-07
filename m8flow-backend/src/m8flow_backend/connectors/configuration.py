from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from m8flow_backend.models.host_base import HostBase


class ConnectorConfigurationModel(HostBase):
    """Named connector profile for one tenant. Secret values are never on this row."""

    __tablename__ = "m8flow_connector_configuration"
    __table_args__ = (
        UniqueConstraint(
            "m8f_tenant_id",
            "connector_type",
            "profile_name",
            name="uq_host_m8flow_connector_configuration_profile",
        ),
        Index(
            "ix_host_m8flow_connector_configuration_tenant_type",
            "m8f_tenant_id",
            "connector_type",
        ),
        Index(
            "ix_host_m8flow_connector_configuration_tenant_active",
            "m8f_tenant_id",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    secret_refs: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "connector_type": self.connector_type,
            "profile_name": self.profile_name,
            "display_name": self.display_name,
            "description": self.description,
            "config": dict(self.config_json or {}),
            "configured_secrets": sorted((self.secret_refs or {}).keys()),
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
