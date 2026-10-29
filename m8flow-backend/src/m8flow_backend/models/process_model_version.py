from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase

# Rows that make a version live. A baseline is the snapshot taken of a model
# that was already published before history existed.
LIVE_ACTIONS: tuple[str, ...] = ("publish", "baseline")


class ProcessModelVersionModel(HostBase):
    """One recorded state of a process model's files (save / publish / revert / baseline).

    The files on disk are the working copy; Start runs the newest `publish` or
    `baseline` row. Written by `catalog.versions`. Schema matches
    migrations/versions/c9d0e1f2a3b4_add_process_model_version.py -- keep in sync.
    """

    __tablename__ = "m8flow_process_model_version"
    __table_args__ = (
        UniqueConstraint(
            "m8f_tenant_id",
            "process_model_identifier",
            "version",
            name="uq_process_model_version_tenant_model_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    process_model_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    # {file_name: {"text": str} | {"base64": str}}; process_model.json excluded.
    files: Mapped[dict] = mapped_column(JSON, nullable=False)
    primary_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reverted_from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
