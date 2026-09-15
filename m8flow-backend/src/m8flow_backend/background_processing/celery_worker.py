"""Celery worker entry. Does not bootstrap spiffworkflow_backend."""

from __future__ import annotations

from m8flow_backend.scheduler import celery_app, poll_due_jobs

app = celery_app

if __name__ == "__main__":
    poll_due_jobs()
