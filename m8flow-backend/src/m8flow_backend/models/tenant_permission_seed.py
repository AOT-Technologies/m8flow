from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase


class M8flowTenantPermissionSeedModel(HostBase):
    """Version of the canonical YAML permission seed applied for a tenant."""

    __tablename__ = "m8flow_tenant_permission_seed"

    m8f_tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    seed_version: Mapped[int] = mapped_column(Integer, nullable=False)
