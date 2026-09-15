from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column


class AuditDateTimeMixin:
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
