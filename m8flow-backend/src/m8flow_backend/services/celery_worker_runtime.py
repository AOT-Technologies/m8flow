from __future__ import annotations

from typing import Any

from sqlalchemy import text


def tenant_id_for_process_instance(engine: Any, process_instance_id: int) -> str | None:
    """Look up a process instance tenant without touching the scoped ORM session."""
    with engine.connect() as connection:
        tenant_id = connection.execute(
            text("SELECT m8f_tenant_id FROM process_instance WHERE id = :process_instance_id"),
            {"process_instance_id": process_instance_id},
        ).scalar()
    if isinstance(tenant_id, str) and tenant_id:
        return tenant_id
    return None


def cleanup_scoped_session(session: Any) -> None:
    """Reset a scoped session between Celery tasks so worker state does not leak."""
    rollback = getattr(session, "rollback", None)
    if callable(rollback):
        try:
            rollback()
        except Exception:
            pass

    remove = getattr(session, "remove", None)
    if callable(remove):
        try:
            remove()
        except Exception:
            pass


def reset_engine_for_worker_process(engine: Any, session: Any) -> None:
    """Dispose inherited DB connections after a Celery prefork child starts."""
    cleanup_scoped_session(session)

    dispose = getattr(engine, "dispose", None)
    if callable(dispose):
        try:
            dispose()
        except Exception:
            pass
