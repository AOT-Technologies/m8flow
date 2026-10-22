from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase


class ProcessModelVersionModel(HostBase):
    """One published snapshot of a process model's files. The highest version
    is the live one Start runs; the spec dir holds the working copy. Schema
    matches migrations/versions/c9d0e1f2a3b4_add_process_model_versions.py --
    keep in sync.
    """

    __tablename__ = "m8flow_process_model_version"
    __table_args__ = (
        UniqueConstraint(
            "m8f_tenant_id",
            "process_model_identifier",
            "version",
            name="uq_process_model_version_tenant",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    process_model_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # {file name: base64 bytes}; process_model.json is metadata, not versioned.
    files: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    # Username; None for the baseline taken from a model published before versioning.
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
