"""Scheduler jobs core creates for timers, run through the host under RLS.

Mirrors ``scheduler.poll_due_jobs``: one tenant bound into the context per
batch, ``workflow.run_due`` given that tenant. ``now`` only selects which jobs
are due; the engine evaluates the timer itself against the wall clock, so the
fixture's timer is two seconds and the test waits for the job's own
``run_at`` rather than a fixed sleep.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from tests.integration.support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

MODEL = "timers/approval"


def _run_due(tenant_id: str, now: datetime) -> int:
    from m8flow_backend import workflow

    with tenant_session(tenant_id) as session:
        return workflow.run_due(session, now=now, worker_id="integration", tenant_id=tenant_id)


def test_intermediate_timer_waits_until_due_then_releases_the_user_task():
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel
    from m8flow_bpmn_core.models.scheduler_job import SchedulerJobModel

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

    time.sleep(max(0.0, (run_at - datetime.now(timezone.utc)).total_seconds()) + 0.2)
    assert _run_due(tenant_id, datetime.now(timezone.utc)) == 1

    with tenant_session(tenant_id) as session:
        assert session.get(ProcessInstanceModel, instance.id).status == "user_input_required"
        titles = [t.task_title for t in workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=editor.id)]
        remaining = session.scalars(
            sa.select(SchedulerJobModel.id).where(SchedulerJobModel.process_instance_id == instance.id)
        ).all()
    assert titles == ["Approve"]
    assert remaining == []
