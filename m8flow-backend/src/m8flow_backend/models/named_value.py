from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from m8flow_backend.models.host_base import HostBase


class NamedValueModel(HostBase):
    """Tenant-scoped catalog metadata for reusable configuration variables."""

    __tablename__ = "m8flow_named_value"
    __table_args__ = (
        CheckConstraint(
            "(is_sensitive = true AND value IS NULL) OR "
            "(is_sensitive = false AND is_configured = false AND value IS NULL) OR "
            "(is_sensitive = false AND is_configured = true AND value IS NOT NULL)",
            name="ck_m8flow_named_value_storage",
        ),
        Index(
            "uq_m8flow_named_value_tenant_name_ci",
            "m8f_tenant_id",
            text("lower(name)"),
            unique=True,
        ),
        Index("ix_m8flow_named_value_tenant", "m8f_tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    m8f_tenant_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("m8flow_tenant.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_sensitive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    # Sensitive values are provider-backed; only ordinary values occupy this column.
    value: Mapped[Any | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    is_configured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    # Legacy provider key during the staged migration; cleared after an ID-keyed
    # provider document is written and verified.
    provider_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
