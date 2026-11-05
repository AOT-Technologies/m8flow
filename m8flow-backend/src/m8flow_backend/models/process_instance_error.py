from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase


class ProcessInstanceErrorModel(HostBase):
    """Why an automatic task failed. Core records a bare ``task_failed`` event
    with no message, so the host keeps the text. Service-task failures are
    written by ``workflow.record_service_task_error`` on a separate committed
    session; user-submission failures are saved with the submission itself.
    Schema matches
    migrations/versions/b7e1c2d3f4a5_add_process_instance_error.py -- keep in sync.
    """

    __tablename__ = "m8flow_process_instance_error"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    m8f_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    process_instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_guid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
