"""Scheduler jobs core creates for timers, run through the host under RLS.

Mirrors ``scheduler.poll_due_jobs``: one tenant bound into the context per
batch, ``workflow.run_due`` given that tenant. ``now`` only selects which jobs
are due; the engine evaluates the timer itself against the wall clock, so the
fixture's timer is two seconds and the test waits for the job's own
``run_at`` rather than a fixed sleep.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from .support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

MODEL = "timers/approval"


def _run_due(tenant_id: str, now: datetime) -> int:
    from m8flow_backend import workflow

    with tenant_session(tenant_id) as session:
        return workflow.run_due(session, now=now, worker_id="integration", tenant_id=tenant_id)


def _wait_for_due_timer(poll: Callable[[], int], *, timeout_seconds: float = 15.0) -> int:
    deadline = time.monotonic() + timeout_seconds
    while True:
        processed = poll()
        if processed:
            return processed

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail(f"Timer poll did not process a due job within {timeout_seconds:g} seconds.")
        time.sleep(min(0.05, remaining))


def test_intermediate_timer_waits_until_due_then_releases_the_user_task():
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.scheduler_job import SchedulerJobModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("timer")
    other_tenant = new_tenant_id("timer-other")
    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(session, tenant_id=tenant_id, user_id=editor.id, path=MODEL, fixture="timer_then_approval.bpmn")
    with tenant_session(tenant_id) as session:
        instance = workflow.start(session, tenant_id=tenant_id, user_id=editor.id, process_model_identifier=MODEL)

    with tenant_session(tenant_id) as session:
        assert session.get(ProcessInstanceModel, instance.id).status == "waiting"
        assert workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=editor.id) == []
        (job,) = session.scalars(
            sa.select(SchedulerJobModel).where(SchedulerJobModel.process_instance_id == instance.id)
        ).all()
        job_type, run_at = job.job_type, job.run_at
    assert job_type == "intermediate_timer"

    # Before run_at nothing is due; another tenant's poll never picks the job up.
    assert _run_due(tenant_id, run_at - timedelta(seconds=1)) == 0
    assert _run_due(other_tenant, run_at + timedelta(hours=1)) == 0

    assert _wait_for_due_timer(lambda: _run_due(tenant_id, datetime.now(timezone.utc))) == 1

    with tenant_session(tenant_id) as session:
        assert session.get(ProcessInstanceModel, instance.id).status == "user_input_required"
        titles = [t.task_title for t in workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=editor.id)]
        remaining = session.scalars(
            sa.select(SchedulerJobModel.id).where(SchedulerJobModel.process_instance_id == instance.id)
        ).all()
    assert titles == ["Approve"]
    assert remaining == []


def test_celery_poll_task_releases_an_expired_intermediate_timer():
    """The registered Celery task executes the same due timer path as the worker."""
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.scheduler_job import SchedulerJobModel

    from m8flow_backend import workflow
    from m8flow_backend.scheduler import poll_due_task

    tenant_id = new_tenant_id("celery-timer")
    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(session, tenant_id=tenant_id, user_id=editor.id, path=MODEL, fixture="timer_then_approval.bpmn")
    with tenant_session(tenant_id) as session:
        instance = workflow.start(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            process_model_identifier=MODEL,
        )

    with tenant_session(tenant_id) as session:
        assert session.get(ProcessInstanceModel, instance.id).status == "waiting"
        (job,) = session.scalars(
            sa.select(SchedulerJobModel).where(SchedulerJobModel.process_instance_id == instance.id)
        ).all()
        assert job.job_type == "intermediate_timer"

    assert _wait_for_due_timer(lambda: poll_due_task.apply().get()) == 1
    # A second poll (for example, overlapping scheduler ticks during a restart)
    # must not execute the same due job or create another downstream task.
    assert poll_due_task.apply().get() == 0

    with tenant_session(tenant_id) as session:
        assert session.get(ProcessInstanceModel, instance.id).status == "user_input_required"
        titles = [
            task.task_title
            for task in workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=editor.id)
        ]
        remaining = session.scalars(
            sa.select(SchedulerJobModel.id).where(SchedulerJobModel.process_instance_id == instance.id)
        ).all()
    assert titles == ["Approve"]
    assert remaining == []


def test_celery_poll_task_processes_due_timers_for_multiple_tenants_isolated():
    """One Beat poll handles each tenant's due timer without crossing tenant data."""
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.scheduler_job import SchedulerJobModel

    from m8flow_backend import workflow
    from m8flow_backend.scheduler import poll_due_task

    tenant_ids = [new_tenant_id("celery-multi-a"), new_tenant_id("celery-multi-b")]
    instances: dict[str, tuple[int, int]] = {}

    for tenant_id in tenant_ids:
        with tenant_session(tenant_id) as session:
            editor = provision_member(session, tenant_id=tenant_id, role="editor")
            save_model(
                session,
                tenant_id=tenant_id,
                user_id=editor.id,
                path=MODEL,
                fixture="timer_then_approval.bpmn",
            )
        with tenant_session(tenant_id) as session:
            instance = workflow.start(
                session,
                tenant_id=tenant_id,
                user_id=editor.id,
                process_model_identifier=MODEL,
            )
            instances[tenant_id] = (instance.id, editor.id)

        # Make each persisted job due so one Beat task invocation can poll both
        # tenants without relying on timer-duration sleeps or CI scheduling.
        with tenant_session(tenant_id) as session:
            (job,) = session.scalars(
                sa.select(SchedulerJobModel).where(
                    SchedulerJobModel.process_instance_id == instance.id
                )
            ).all()
            assert job.job_type == "intermediate_timer"
            job.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert poll_due_task.apply().get() == 2

    for index, tenant_id in enumerate(tenant_ids):
        instance_id, editor_id = instances[tenant_id]
        other_instance_id = instances[tenant_ids[1 - index]][0]
        with tenant_session(tenant_id) as session:
            instance = session.get(ProcessInstanceModel, instance_id)
            assert instance is not None
            assert instance.status == "user_input_required"
            # The other tenant's row is hidden by RLS in this tenant's session.
            assert session.get(ProcessInstanceModel, other_instance_id) is None

            tasks = workflow.list_pending_tasks(
                session,
                tenant_id=tenant_id,
                user_id=editor_id,
            )
            assert [task.task_title for task in tasks] == ["Approve"]
            remaining_jobs = session.scalars(
                sa.select(SchedulerJobModel.id).where(
                    SchedulerJobModel.process_instance_id == instance_id
                )
            ).all()
            assert remaining_jobs == []
