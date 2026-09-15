from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class M8fTenantScopedMixin:
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)


class TenantScoped:
    pass
