from __future__ import annotations

import os
import time

from sqlalchemy import select

from m8flow_backend import workflow
from m8flow_backend.db import session_scope
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from m8flow_backend.scheduler.celery_tenant import TenantAwareCelery, install_celery_tenant_signals
from m8flow_backend.auth.tenant_context import reset_context_tenant_id, set_context_tenant_id


def _active_tenant_ids(session) -> list[str]:
    return list(
        session.scalars(
            select(M8flowTenantModel.id)
            .where(M8flowTenantModel.status == TenantStatus.ACTIVE)
            .order_by(M8flowTenantModel.id)
        ).all()
    )


def poll_due_jobs(*, limit: int = 100, worker_id: str | None = None) -> int:
    """Run due scheduler jobs per active tenant.

    Beat has no HTTP tenant. Passing ``tenant_id=None`` into ``workflow.run_due``
    mixes tenants on SQLite and sees no rows under PostgreSQL RLS. Bind each
    active tenant into the ContextVar (so ``SET LOCAL`` matches request-time
    RLS) and pass that id into core.
    """
    worker = worker_id or os.environ.get("M8FLOW_SCHEDULER_WORKER_ID") or "celery"
    now = int(time.time())
    with session_scope() as session:
        tenant_ids = _active_tenant_ids(session)

    processed = 0
    remaining = limit
    for tenant_id in tenant_ids:
        if remaining <= 0:
            break
        token = set_context_tenant_id(tenant_id)
        try:
            with session_scope() as session:
                processed += workflow.run_due(
                    session,
                    now_in_seconds=now,
                    limit=remaining,
                    worker_id=worker,
                    tenant_id=tenant_id,
                )
            remaining = limit - processed
        finally:
            reset_context_tenant_id(token)
    return processed


def create_celery_app():
    app = TenantAwareCelery("m8flow_backend")
    broker = os.environ.get("M8FLOW_CELERY_BROKER_URL") or os.environ.get(
        "SPIFFWORKFLOW_BACKEND_CELERY_BROKER_URL"
    ) or "redis://localhost:6379/0"
    app.conf.broker_url = broker
    app.conf.result_backend = broker
    app.conf.beat_schedule = {
        "m8flow-run-due": {
            "task": "m8flow_backend.scheduler.poll_due_task",
            "schedule": float(os.environ.get("M8FLOW_SCHEDULER_POLL_SECONDS") or 10),
        }
    }
    install_celery_tenant_signals()
    return app


celery_app = create_celery_app()


@celery_app.task(name="m8flow_backend.scheduler.poll_due_task")
def poll_due_task() -> int:
    return poll_due_jobs()
