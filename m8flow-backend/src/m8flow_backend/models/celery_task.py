from __future__ import annotations

import enum
from datetime import datetime

from typing import ClassVar

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from m8flow_backend.models.host_base import HostBase


class CeleryTaskState(str, enum.Enum):
    """Celery's own state names, as Flower shows them."""

    RECEIVED = "RECEIVED"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"
    REVOKED = "REVOKED"


FINISHED_STATES = (CeleryTaskState.SUCCESS.value, CeleryTaskState.FAILURE.value, CeleryTaskState.REVOKED.value)

INDEXED_COLUMNS: tuple[str, ...] = ("name", "state", "worker", "tenant_id", "updated_at")


class CeleryTaskModel(HostBase):
    """One row per Celery task, updated as the task moves through a worker (M8F-602).

    Celery keeps no task history (Flower rebuilds one in memory from worker events), so the
    worker records it here from its own task signals; see
    ``services/celery_task_history_service.py``. Global operations data read by
    super-admins only: there is deliberately no ``m8f_tenant_id`` column, so the root
    migration's row-level-security policy does not apply and a worker can record tasks
    that run without a tenant. The tenant a task ran for is kept in ``tenant_id`` for
    display. Arguments, results and tracebacks are stored redacted and truncated.

    Schema matches migrations/versions/a8c1e2f3b4d5_add_celery_task_history.py -- keep the
    two in sync.
    """

    __tablename__ = "m8flow_celery_task"
    INDEXED_COLUMNS: ClassVar[tuple[str, ...]] = INDEXED_COLUMNS

    task_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    worker: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    queue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    args: Mapped[str | None] = mapped_column(Text, nullable=True)
    kwargs: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eta: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    root_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The recorder always sets it; the database default covers any other writer.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True, server_default=func.now())
