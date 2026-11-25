"""Concurrency regression coverage for catalog writes and timer publication."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
import sqlalchemy as sa

from m8flow_core.models.bpmn_process_definition import (
    BpmnProcessDefinitionModel,
    PROCESS_MODEL_IDENTIFIER_PROPERTY_KEY,
)
from m8flow_core.models.scheduler_job import SchedulerJobModel

from m8flow_backend import catalog, workflow

from .support import new_tenant_id, provision_member, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

MODEL_ID = "timers/publish-race"
BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 targetNamespace="https://example.test/timers">
  <bpmn:process id="Process_publish_race" isExecutable="true">
    <bpmn:startEvent id="Start_timer">
      <bpmn:timerEventDefinition>
        <bpmn:timeCycle xsi:type="bpmn:tFormalExpression">'R/PT5M'</bpmn:timeCycle>
      </bpmn:timerEventDefinition>
    </bpmn:startEvent>
    <bpmn:sequenceFlow id="flow_start_end" sourceRef="Start_timer" targetRef="End_event" />
    <bpmn:endEvent id="End_event" />
  </bpmn:process>
</bpmn:definitions>
"""


def test_concurrent_save_and_publish_reconciliation_leave_one_timer_schedule(
    monkeypatch, tmp_path
):
    tenant_id = new_tenant_id("timer-publish-race")
    monkeypatch.setenv(
        "M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "specs")
    )

    with tenant_session(tenant_id) as session:
        user = provision_member(session, tenant_id=tenant_id, role="tenant-admin")
        user_id = user.id
        catalog.add_process_model(
            {
                "id": MODEL_ID,
                "display_name": "Timer publish race",
                "status": catalog.PROCESS_MODEL_STATUS_DRAFT,
                "primary_file_name": "timer.bpmn",
            },
            tenant_id=tenant_id,
        )
        catalog.write_spec_file(
            tenant_id=tenant_id,
            path=MODEL_ID,
            file_name="timer.bpmn",
            content=BPMN.encode("utf-8"),
        )
        catalog.save(
            session,
            path=MODEL_ID,
            xml=BPMN,
            tenant_id=tenant_id,
            user_id=user_id,
        )

    identity = catalog.update_process_model_metadata(
        tenant_id=tenant_id,
        process_model_identifier=MODEL_ID,
        status=catalog.PROCESS_MODEL_STATUS_PUBLISHED,
    )
    with tenant_session(tenant_id) as session:
        workflow.reconcile_process_model_timer_starts(
            session,
            tenant_id=tenant_id,
            process_model_identifier=MODEL_ID,
            status=identity["status"],
            user_id=user_id,
        )

    barrier = Barrier(2)

    def save_published_model() -> None:
        with tenant_session(tenant_id) as session:
            barrier.wait(timeout=10)
            catalog.save(
                session,
                path=MODEL_ID,
                xml=BPMN,
                tenant_id=tenant_id,
                user_id=user_id,
                file_name="timer.bpmn",
            )

    def reconcile_publish() -> None:
        with tenant_session(tenant_id) as session:
            barrier.wait(timeout=10)
            workflow.reconcile_process_model_timer_starts(
                session,
                tenant_id=tenant_id,
                process_model_identifier=MODEL_ID,
                status=catalog.PROCESS_MODEL_STATUS_PUBLISHED,
                user_id=user_id,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(save_published_model), executor.submit(reconcile_publish)]
        for future in futures:
            future.result(timeout=30)

    with tenant_session(tenant_id) as session:
        definition_ids = list(
            session.scalars(
                sa.select(BpmnProcessDefinitionModel.id).where(
                    BpmnProcessDefinitionModel.m8f_tenant_id == tenant_id,
                    BpmnProcessDefinitionModel.properties_json[
                        PROCESS_MODEL_IDENTIFIER_PROPERTY_KEY
                    ].as_string()
                    == MODEL_ID,
                )
            ).all()
        )
        jobs = list(
            session.scalars(
                sa.select(SchedulerJobModel)
                .where(
                    SchedulerJobModel.m8f_tenant_id == tenant_id,
                    SchedulerJobModel.bpmn_process_definition_id.in_(definition_ids),
                    SchedulerJobModel.job_type.in_(workflow._TIMER_START_JOB_TYPES),
                )
                .order_by(SchedulerJobModel.id)
            ).all()
        )
        schedules = workflow.list_process_model_timer_start_schedules(
            session,
            tenant_id=tenant_id,
            process_model_identifier=MODEL_ID,
        )

    assert len(schedules) == 1
    assert len(jobs) == 1
    assert jobs[0].job_type == "timer_start"
    assert jobs[0].bpmn_process_definition_id in definition_ids
    assert jobs[0].run_at.replace(tzinfo=timezone.utc) >= datetime.now(timezone.utc)
