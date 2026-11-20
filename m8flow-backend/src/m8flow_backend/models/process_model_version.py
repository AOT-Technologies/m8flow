from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase


class ProcessModelState(HostBase):
    __tablename__ = "m8flow_process_model_state"

    m8f_tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    generation: Mapped[str] = mapped_column(String(32), nullable=False)
    working_revision: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    working: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    latest_version: Mapped[int | None] = mapped_column(Integer)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProcessModelRelease(HostBase):
    __tablename__ = "m8flow_process_model_release"

    m8f_tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    generation: Mapped[str] = mapped_column(String(32), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    contents: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[str | None] = mapped_column(String(255))


class ProcessInstanceCalledReleases(HostBase):
    __tablename__ = "m8flow_process_instance_called_releases"

    m8f_tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    process_instance_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    releases: Mapped[dict[str, dict[str, str]]] = mapped_column(JSON, nullable=False)
