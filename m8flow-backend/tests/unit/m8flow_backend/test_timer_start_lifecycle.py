from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from m8flow_core.models.bpmn_process_definition import (
    BpmnProcessDefinitionModel,
    PROCESS_MODEL_IDENTIFIER_PROPERTY_KEY,
)
from m8flow_core.models.process_instance import ProcessInstanceModel
from m8flow_core.models.scheduler_job import SchedulerJobModel

from m8flow_backend import catalog, workflow
from m8flow_backend.catalog import versions
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.identity import (
    ensure_membership,
    ensure_tenant,
    ensure_user,
    sync_groups,
)
from m8flow_core.services.authorization import ROLE_ADMIN, ensure_v1_role


TIMER_START_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 targetNamespace="https://example.test/timers">
  <bpmn:process id="Process_timer_lifecycle" isExecutable="true">
    <bpmn:startEvent id="Start_timer">
      <bpmn:timerEventDefinition>
        <bpmn:timeCycle xsi:type="bpmn:tFormalExpression">'R/PT5M'</bpmn:timeCycle>
      </bpmn:timerEventDefinition>
    </bpmn:startEvent>
    <bpmn:sequenceFlow id="flow_start_task" sourceRef="Start_timer" targetRef="Task_review" />
    <bpmn:userTask id="Task_review" name="Review timer occurrence" />
    <bpmn:sequenceFlow id="flow_task_end" sourceRef="Task_review" targetRef="End_event" />
    <bpmn:endEvent id="End_event" />
  </bpmn:process>
</bpmn:definitions>
"""
FAILING_TIMER_START_BPMN = TIMER_START_BPMN.replace(
    '<bpmn:userTask id="Task_review" name="Review timer occurrence" />',
    '''<bpmn:scriptTask id="Task_review" name="Failing timer script">
      <bpmn:script>raise Exception("scheduled script failed")</bpmn:script>
    </bpmn:scriptTask>''',
)


def _seed_model(
    session,
    monkeypatch,
    tmp_path,
    *,
    tenant_id: str,
    model_id: str,
    bpmn: str = TIMER_START_BPMN,
):
    monkeypatch.setenv(
        "M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "specs")
    )
    tenant = ensure_tenant(session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(
        session,
        username=f"timer-admin-{tenant_id}",
        service="https://example.test/realms/m8flow",
        service_id=f"timer-admin-{tenant_id}",
        email=f"timer-admin-{tenant_id}@example.test",
    )
    ensure_membership(session, user, tenant)
    ensure_v1_role(
        session,
        tenant_id=tenant_id,
        role_name=ROLE_ADMIN,
        user_ids=[user.id],
    )
    catalog.add_process_model(
        {
            "id": model_id,
            "display_name": "Timer lifecycle",
            "status": catalog.PROCESS_MODEL_STATUS_DRAFT,
            "primary_file_name": "timer.bpmn",
        },
        tenant_id=tenant_id,
    )
    catalog.write_spec_file(
        tenant_id=tenant_id,
        path=model_id,
        file_name="timer.bpmn",
        content=bpmn.encode("utf-8"),
    )
    catalog.save(
        session,
        path=model_id,
        xml=bpmn,
        tenant_id=tenant_id,
        user_id=user.id,
    )
    return user


def _timer_jobs(session, tenant_id: str, model_id: str):
    definition_ids = sa.select(BpmnProcessDefinitionModel.id).where(
        BpmnProcessDefinitionModel.m8f_tenant_id == tenant_id,
        BpmnProcessDefinitionModel.properties_json[
            PROCESS_MODEL_IDENTIFIER_PROPERTY_KEY
        ].as_string()
        == model_id,
    )
    return list(
        session.scalars(
            sa.select(SchedulerJobModel)
            .where(
                SchedulerJobModel.m8f_tenant_id == tenant_id,
                SchedulerJobModel.bpmn_process_definition_id.in_(definition_ids),
                SchedulerJobModel.job_type.in_(("timer_start", "timer_start_occurrence")),
            )
            .order_by(SchedulerJobModel.job_type, SchedulerJobModel.run_at)
        ).all()
    )


def test_catalog_save_acquires_tenant_lock_once_before_import(
    db_session, monkeypatch, tmp_path
):
    tenant_id = "timer-lock-contract-tenant"
    lock_and_import_order = []
    original_lock = versions.lock_tenant
    original_import = workflow.import_definition

    def record_lock(session, requested_tenant_id):
        lock_and_import_order.append(("lock", requested_tenant_id))
        return original_lock(session, requested_tenant_id)

    def record_import(*args, **kwargs):
        lock_and_import_order.append(("import", kwargs["tenant_id"]))
        return original_import(*args, **kwargs)

    monkeypatch.setattr(versions, "lock_tenant", record_lock)
    monkeypatch.setattr(workflow, "import_definition", record_import)
    _seed_model(
        db_session,
        monkeypatch,
        tmp_path,
        tenant_id=tenant_id,
        model_id="timers/lock-contract",
    )

    assert lock_and_import_order == [("lock", tenant_id), ("import", tenant_id)]


def test_first_catalog_save_creates_model_when_model_directory_is_missing(
    db_session, monkeypatch, tmp_path
):
    tenant_id = "timer-first-save-tenant"
    model_id = "timers/first-save"
    monkeypatch.setenv(
        "M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "specs")
    )
    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(
        db_session,
        username="timer-first-save-admin",
        service="https://example.test/realms/m8flow",
        service_id="timer-first-save-admin",
    )
    ensure_membership(db_session, user, tenant)
    ensure_v1_role(
        db_session,
        tenant_id=tenant_id,
        role_name=ROLE_ADMIN,
        user_ids=[user.id],
    )
    model_dir = tmp_path / "specs" / tenant_id / model_id
    assert not model_dir.exists()

    catalog.save(
        db_session,
        path=model_id,
        xml=TIMER_START_BPMN,
        tenant_id=tenant_id,
        user_id=user.id,
    )

    assert (model_dir / "first-save.bpmn").read_text(encoding="utf-8") == TIMER_START_BPMN


def test_saving_secondary_bpmn_preserves_primary_timer_start_schedule(
    db_session, monkeypatch, tmp_path
):
    tenant_id = "timer-secondary-file-tenant"
    model_id = "timers/secondary-file"
    user = _seed_model(
        db_session,
        monkeypatch,
        tmp_path,
        tenant_id=tenant_id,
        model_id=model_id,
    )

    published = catalog.update_process_model_metadata(
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=catalog.PROCESS_MODEL_STATUS_PUBLISHED,
    )
    workflow.reconcile_process_model_timer_starts(
        db_session,
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=published["status"],
        user_id=user.id,
    )
    primary_job = next(
        job for job in _timer_jobs(db_session, tenant_id, model_id)
        if job.job_type == "timer_start"
    )
    primary_job_id = primary_job.id
    primary_run_at = primary_job.run_at

    secondary_bpmn = TIMER_START_BPMN.replace(
        "Process_timer_lifecycle", "Process_secondary_timer"
    )
    catalog.save(
        db_session,
        path=model_id,
        file_name="secondary.bpmn",
        xml=secondary_bpmn,
        tenant_id=tenant_id,
        user_id=user.id,
    )

    jobs = _timer_jobs(db_session, tenant_id, model_id)
    assert len(jobs) == 1
    assert jobs[0].id == primary_job_id
    assert jobs[0].run_at == primary_run_at


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect()])
def test_timer_start_model_identifier_json_filter_compiles_for_supported_dialects(dialect):
    """The JSON text filter used by reconcile/list queries must compile on SQLite and PG."""
    expression = (
        BpmnProcessDefinitionModel.properties_json[
            PROCESS_MODEL_IDENTIFIER_PROPERTY_KEY
        ].as_string()
        == "timers/recurring"
    )
    statement = sa.select(BpmnProcessDefinitionModel.id).where(expression)

    compiled = statement.compile(dialect=dialect)
    assert "bpmn_process_definition" in str(compiled)
    assert "timers/recurring" in compiled.params.values()


def _poll_twice(session, *, tenant_id: str) -> None:
    now = datetime.now(timezone.utc)
    assert workflow.run_due(
        session,
        now=now,
        worker_id="timer-lifecycle-test",
        tenant_id=tenant_id,
    ) == 1
    session.flush()
    assert workflow.run_due(
        session,
        now=now + timedelta(seconds=1),
        worker_id="timer-lifecycle-test",
        tenant_id=tenant_id,
    ) == 1
    session.flush()


def _poll_celery_twice(expected_jobs: int = 1) -> None:
    from m8flow_backend.scheduler import poll_due_task

    assert poll_due_task.apply().get() == expected_jobs
    # Newer core versions may persist a separate immediately-due occurrence
    # job after processing the recurring schedule. The pinned b3 release
    # handles the occurrence in the first job. In both cases, assert the
    # resulting instances below and drain any immediate follow-up work.
    assert poll_due_task.apply().get() in (0, expected_jobs)
    assert poll_due_task.apply().get() == 0


def test_timer_start_lifecycle_publishes_recurring_independent_instances_and_pauses(
    db_session, monkeypatch, tmp_path
):
    tenant_id = "timer-lifecycle-tenant"
    model_id = "timers/recurring"
    user = _seed_model(
        db_session,
        monkeypatch,
        tmp_path,
        tenant_id=tenant_id,
        model_id=model_id,
    )

    # A draft definition must not retain the timer job that core creates while
    # importing BPMN. No manual workflow.start() call is made in this test.
    assert _timer_jobs(db_session, tenant_id, model_id) == []
    assert db_session.scalars(
        sa.select(ProcessInstanceModel.id).where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id
        )
    ).all() == []

    identity = catalog.update_process_model_metadata(
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=catalog.PROCESS_MODEL_STATUS_PUBLISHED,
    )
    workflow.reconcile_process_model_timer_starts(
        db_session,
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=identity["status"],
        user_id=user.id,
    )
    jobs = _timer_jobs(db_session, tenant_id, model_id)
    assert [job.job_type for job in jobs] == ["timer_start"]
    # This query uses the same JSON `.as_string()` filter against SQLite that
    # production uses against PostgreSQL; assert the API metadata query sees
    # only this tenant/model's active timer-start row.
    schedules = workflow.list_process_model_timer_start_schedules(
        db_session,
        tenant_id=tenant_id,
        process_model_identifier=model_id,
    )
    assert len(schedules) == 1
    assert schedules[0]["next_run_at"] == jobs[0].run_at.isoformat()

    # Repeating the same publish reconciliation must reuse the active
    # definition and preserve its scheduled fire time instead of importing a
    # second definition and resetting the recurring timer.
    active_job_id = jobs[0].id
    active_run_at = jobs[0].run_at
    definition_count = db_session.scalar(
        sa.select(sa.func.count(BpmnProcessDefinitionModel.id)).where(
            BpmnProcessDefinitionModel.m8f_tenant_id == tenant_id,
            BpmnProcessDefinitionModel.properties_json[
                PROCESS_MODEL_IDENTIFIER_PROPERTY_KEY
            ].as_string()
            == model_id,
        )
    )
    workflow.reconcile_process_model_timer_starts(
        db_session,
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=identity["status"],
        user_id=user.id,
    )
    jobs = _timer_jobs(db_session, tenant_id, model_id)
    assert len(jobs) == 1
    assert jobs[0].id == active_job_id
    assert jobs[0].run_at == active_run_at
    assert db_session.scalar(
        sa.select(sa.func.count(BpmnProcessDefinitionModel.id)).where(
            BpmnProcessDefinitionModel.m8f_tenant_id == tenant_id,
            BpmnProcessDefinitionModel.properties_json[
                PROCESS_MODEL_IDENTIFIER_PROPERTY_KEY
            ].as_string()
            == model_id,
        )
    ) == definition_count

    now = datetime.now(timezone.utc)
    jobs[0].run_at = now - timedelta(seconds=1)
    db_session.commit()
    _poll_twice(db_session, tenant_id=tenant_id)
    first_id = db_session.scalar(
        sa.select(ProcessInstanceModel.id).where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id
        )
    )
    assert first_id is not None
    assert db_session.get(ProcessInstanceModel, first_id).status == "user_input_required"

    # The first instance remains waiting on its user task while a later cycle
    # occurrence creates a separate process instance.
    recurring = next(job for job in _timer_jobs(db_session, tenant_id, model_id) if job.job_type == "timer_start")
    recurring.run_at = now - timedelta(seconds=1)
    db_session.commit()
    _poll_twice(db_session, tenant_id=tenant_id)
    instance_ids = db_session.scalars(
        sa.select(ProcessInstanceModel.id)
        .where(ProcessInstanceModel.m8f_tenant_id == tenant_id)
        .order_by(ProcessInstanceModel.id)
    ).all()
    assert len(instance_ids) == 2
    assert all(db_session.get(ProcessInstanceModel, instance_id).status == "user_input_required" for instance_id in instance_ids)
    assert workflow.run_due(
        db_session,
        now=now + timedelta(seconds=5),
        worker_id="timer-lifecycle-test",
        tenant_id=tenant_id,
    ) == 0

    # Pause after the schedule row has created an occurrence but before that
    # occurrence starts a process. Both kinds of pending timer-start work must
    # be removed by the lifecycle transition.
    recurring = next(
        job for job in _timer_jobs(db_session, tenant_id, model_id) if job.job_type == "timer_start"
    )
    recurring.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert workflow.run_due(
        db_session,
        now=datetime.now(timezone.utc),
        worker_id="timer-lifecycle-test",
        tenant_id=tenant_id,
    ) == 1
    assert {job.job_type for job in _timer_jobs(db_session, tenant_id, model_id)} == {
        "timer_start",
        "timer_start_occurrence",
    }

    paused = catalog.update_process_model_metadata(
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=catalog.PROCESS_MODEL_STATUS_PAUSED,
    )
    workflow.reconcile_process_model_timer_starts(
        db_session,
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=paused["status"],
        user_id=user.id,
    )
    assert _timer_jobs(db_session, tenant_id, model_id) == []
    db_session.commit()

    republished = catalog.update_process_model_metadata(
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=catalog.PROCESS_MODEL_STATUS_PUBLISHED,
    )
    workflow.reconcile_process_model_timer_starts(
        db_session,
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=republished["status"],
        user_id=user.id,
    )
    db_session.commit()
    assert [job.job_type for job in _timer_jobs(db_session, tenant_id, model_id)] == [
        "timer_start"
    ]


def test_process_model_api_publication_reconciles_timer_start_jobs(
    client, db_session, monkeypatch, tmp_path
):
    """Exercise the catalog lifecycle through the same API used by the designer."""
    tenant_id = "timer-api-lifecycle-tenant"
    model_id = "timers/api-published"
    user = _seed_model(
        db_session,
        monkeypatch,
        tmp_path,
        tenant_id=tenant_id,
        model_id=model_id,
    )
    user = ensure_user(
        db_session,
        username=f"timer-api-editor-{tenant_id}",
        service="https://example.test/realms/m8flow",
        service_id=f"timer-api-editor-{tenant_id}",
    )
    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    ensure_membership(db_session, user, tenant)
    sync_groups(
        db_session,
        user=user,
        group_identifiers=[f"{tenant_id}:editor"],
        tenant_id=tenant_id,
    )
    from m8flow_core.services.authorization import ensure_v1_role as ensure_core_v1_role

    ensure_core_v1_role(db_session, tenant_id=tenant_id, role_name="admin", user_ids=(user.id,))
    # The ASGI request and Celery task each open their own SQLAlchemy session.
    # Commit fixture setup before invoking them to avoid holding SQLite's write
    # lock from the test session while the request authenticates.
    db_session.commit()
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    headers = {"Authorization": f"Bearer {encode_auth_token(user=user)}"}
    model_url = "/v1.0/m8flow/process-models/timers:api-published"

    # Draft has no timer jobs. Publishing through the API imports/synchronizes
    # the model's current primary BPMN. The test then checks both the scheduled
    # path and the ordinary manual-start endpoint against that published model.
    assert _timer_jobs(db_session, tenant_id, model_id) == []
    published = client.put(model_url, headers=headers, json={"status": "published"})
    assert published.status_code == 200, published.get_json()
    jobs = _timer_jobs(db_session, tenant_id, model_id)
    assert [job.job_type for job in jobs] == ["timer_start"]

    # Publishing a timer-start model also leaves the ordinary manual start
    # action available. It creates one independent instance without consuming
    # or duplicating the recurring scheduler record.
    start_url = f"{model_url}/start"
    manual_start = client.post(start_url, headers=headers)
    assert manual_start.status_code == 201, manual_start.get_json()
    manual_instance_id = manual_start.get_json()["id"]
    assert len(_timer_jobs(db_session, tenant_id, model_id)) == 1
    assert db_session.scalar(
        sa.select(sa.func.count(ProcessInstanceModel.id)).where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id
        )
    ) == 1

    jobs[0].run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    _poll_celery_twice()
    assert db_session.scalar(
        sa.select(sa.func.count(ProcessInstanceModel.id)).where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id
        )
    ) == 2
    scheduled_instance_ids = db_session.scalars(
        sa.select(ProcessInstanceModel.id).where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id,
            ProcessInstanceModel.id != manual_instance_id,
        )
    ).all()
    assert len(scheduled_instance_ids) == 1

    # Both pause and unpublish stop already queued future starts/occurrences.
    paused = client.put(model_url, headers=headers, json={"status": "paused"})
    assert paused.status_code == 200, paused.get_json()
    assert _timer_jobs(db_session, tenant_id, model_id) == []
    assert client.post(start_url, headers=headers).status_code == 409

    republished = client.put(model_url, headers=headers, json={"status": "published"})
    assert republished.status_code == 200, republished.get_json()
    assert [job.job_type for job in _timer_jobs(db_session, tenant_id, model_id)] == [
        "timer_start"
    ]
    resumed_manual_start = client.post(start_url, headers=headers)
    assert resumed_manual_start.status_code == 201, resumed_manual_start.get_json()
    assert len(_timer_jobs(db_session, tenant_id, model_id)) == 1

    unpublished = client.put(model_url, headers=headers, json={"status": "draft"})
    assert unpublished.status_code == 200, unpublished.get_json()
    assert _timer_jobs(db_session, tenant_id, model_id) == []
    assert client.post(start_url, headers=headers).status_code == 409


def test_failed_timer_started_instance_does_not_stop_later_occurrences(
    db_session, monkeypatch, tmp_path
):
    tenant_id = "timer-failure-tenant"
    model_id = "timers/failing"
    user = _seed_model(
        db_session,
        monkeypatch,
        tmp_path,
        tenant_id=tenant_id,
        model_id=model_id,
        bpmn=FAILING_TIMER_START_BPMN,
    )
    identity = catalog.update_process_model_metadata(
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=catalog.PROCESS_MODEL_STATUS_PUBLISHED,
    )
    workflow.reconcile_process_model_timer_starts(
        db_session,
        tenant_id=tenant_id,
        process_model_identifier=model_id,
        status=identity["status"],
        user_id=user.id,
    )

    now = datetime.now(timezone.utc)
    next_occurrence = next(
        job for job in _timer_jobs(db_session, tenant_id, model_id) if job.job_type == "timer_start"
    )
    next_occurrence.run_at = now - timedelta(seconds=1)
    db_session.commit()
    _poll_twice(db_session, tenant_id=tenant_id)
    instance = db_session.scalar(
        sa.select(ProcessInstanceModel).where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id
        )
    )
    assert instance is not None
    assert instance.status == "error"

    recurring = next(
        job for job in _timer_jobs(db_session, tenant_id, model_id) if job.job_type == "timer_start"
    )
    recurring.run_at = now - timedelta(seconds=1)
    db_session.commit()
    _poll_twice(db_session, tenant_id=tenant_id)
    instances = db_session.scalars(
        sa.select(ProcessInstanceModel).where(
            ProcessInstanceModel.m8f_tenant_id == tenant_id
        )
    ).all()
    assert len(instances) == 2
    assert all(instance.status == "error" for instance in instances)


def test_celery_timer_start_poll_is_tenant_isolated(
    db_session, monkeypatch, tmp_path
):
    tenant_ids = ("timer-poll-tenant-a", "timer-poll-tenant-b")
    model_id = "timers/isolated"
    for tenant_id in tenant_ids:
        user = _seed_model(
            db_session,
            monkeypatch,
            tmp_path,
            tenant_id=tenant_id,
            model_id=model_id,
        )
        identity = catalog.update_process_model_metadata(
            tenant_id=tenant_id,
            process_model_identifier=model_id,
            status=catalog.PROCESS_MODEL_STATUS_PUBLISHED,
        )
        workflow.reconcile_process_model_timer_starts(
            db_session,
            tenant_id=tenant_id,
            process_model_identifier=model_id,
            status=identity["status"],
            user_id=user.id,
        )
        next_occurrence = next(
            job
            for job in _timer_jobs(db_session, tenant_id, model_id)
            if job.job_type == "timer_start"
        )
        next_occurrence.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    _poll_celery_twice(expected_jobs=2)
    db_session.expire_all()
    for tenant_id in tenant_ids:
        instances = db_session.scalars(
            sa.select(ProcessInstanceModel).where(
                ProcessInstanceModel.m8f_tenant_id == tenant_id
            )
        ).all()
        assert len(instances) == 1
        assert instances[0].status == "user_input_required"
