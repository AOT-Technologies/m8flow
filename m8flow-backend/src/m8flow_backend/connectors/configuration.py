from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
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
            "uq_host_m8flow_connector_configuration_id_tenant",
            "id",
            "m8f_tenant_id",
            unique=True,
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
    variables: Mapped[list[ConnectorVariableModel]] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
    )
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nullable while legacy profiles are being converted to the provider-document format.
    provider_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
            # Never serialized: only the show route fills this, for editors,
            # with prefill-safe values. Runtime reads config_json directly.
            "config": {},
            "configured_secrets": sorted((self.secret_refs or {}).keys()),
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ConnectorVariableModel(HostBase):
    """One descriptor-defined field belonging to a tenant connector profile."""

    __tablename__ = "m8flow_connector_variable"
    __table_args__ = (
        UniqueConstraint(
            "connector_configuration_id",
            "field_name",
            name="uq_m8flow_connector_variable_field",
        ),
        ForeignKeyConstraint(
            ["connector_configuration_id", "m8f_tenant_id"],
            [
                "m8flow_connector_configuration.id",
                "m8flow_connector_configuration.m8f_tenant_id",
            ],
            name="fk_m8flow_connector_variable_configuration_tenant",
            ondelete="CASCADE",
        ),
        Index(
            "ix_m8flow_connector_variable_tenant_configuration",
            "m8f_tenant_id",
            "connector_configuration_id",
        ),
        Index("ix_m8flow_connector_variable_tenant", "m8f_tenant_id"),
        CheckConstraint(
            "(is_sensitive = false) OR (value IS NULL)",
            name="ck_m8flow_connector_variable_sensitive_value",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    m8f_tenant_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("m8flow_tenant.id"),
        nullable=False,
    )
    connector_configuration_id: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[ConnectorConfigurationModel] = relationship(
        back_populates="variables",
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Legacy key retained until the new provider-document API is introduced.
    provider_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value: Mapped[Any | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    is_configured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
