from __future__ import annotations

from m8flow_backend import workflow

TENANT = "tenant-a"
PI_ID = 700


def _user(session, *, uid, username, display_name=None):
    from m8flow_bpmn_core.models.user import UserModel

    session.add(
        UserModel(
            id=uid,
            username=username,
            display_name=display_name,
            service="https://example.test/realms/m8flow",
            service_id=f"svc-{uid}",
        )
    )
    session.flush()


def _human_task(
    session,
    *,
    task_name,
    status,
    completed,
    created_at,
    actual_owner_id=None,
    completed_by_user_id=None,
    lane_name=None,
    updated_at=None,
):
    from m8flow_bpmn_core.models.human_task import HumanTaskModel

    ht = HumanTaskModel(
        m8f_tenant_id=TENANT,
        process_instance_id=PI_ID,
        task_name=task_name,
        task_title=task_name,
        task_type="UserTask",
        task_status=status,
        process_model_display_name="Approval",
        bpmn_process_identifier="finance/approval",
        completed=completed,
        actual_owner_id=actual_owner_id,
        completed_by_user_id=completed_by_user_id,
        lane_name=lane_name,
        created_at_in_seconds=created_at,
        updated_at_in_seconds=updated_at,
    )
    session.add(ht)
    session.flush()
    return ht


def test_approval_chain_ordering_names_and_null_completer(db_session):
    _user(db_session, uid=1, username="priya", display_name="Priya Nair")
    _user(db_session, uid=2, username="manager", display_name=None)

    # Out of insert order to prove ordering is by created_at, then id.
    _human_task(
        db_session,
        task_name="manager_review",
        status="READY",
        completed=False,
        created_at=2000,
        actual_owner_id=2,
        lane_name="Manager",
    )
    _human_task(
        db_session,
        task_name="submit_claim",
        status="COMPLETED",
        completed=True,
        created_at=1000,
        completed_by_user_id=1,
        actual_owner_id=1,
        updated_at=1500,
    )
    # System-inactivated task: completed but no human owner/completer.
    _human_task(
        db_session,
        task_name="auto_step",
        status="COMPLETED",
        completed=True,
        created_at=1800,
        updated_at=1850,
    )

    chain = workflow.list_human_tasks_for_instance(
        db_session, tenant_id=TENANT, process_instance_id=PI_ID
    )
    assert [row["status"] for row in chain] == ["COMPLETED", "COMPLETED", "READY"]
    # First: completer/owner display name resolved.
    assert chain[0] == {
        "name": "Priya Nair",
        "status": "COMPLETED",
        "completed": True,
        "is_current": False,
        "lane_name": None,
        "completed_at_in_seconds": 1500,
    }
    # Second: system-completed -> name None, completed_at from updated_at.
    assert chain[1]["name"] is None
    assert chain[1]["completed"] is True
    assert chain[1]["completed_at_in_seconds"] == 1850
    # Third: current task -> username fallback (no display_name), no completed_at.
    assert chain[2] == {
        "name": "manager",
        "status": "READY",
        "completed": False,
        "is_current": True,
        "lane_name": "Manager",
        "completed_at_in_seconds": None,
    }


def test_approval_chain_is_tenant_scoped(db_session):
    _user(db_session, uid=1, username="priya", display_name="Priya Nair")
    _human_task(
        db_session,
        task_name="mine",
        status="READY",
        completed=False,
        created_at=1000,
        actual_owner_id=1,
    )
    # Same instance id, different tenant -> must not leak.
    from m8flow_bpmn_core.models.human_task import HumanTaskModel

    db_session.add(
        HumanTaskModel(
            m8f_tenant_id="other-tenant",
            process_instance_id=PI_ID,
            task_name="theirs",
            task_type="UserTask",
            task_status="READY",
            process_model_display_name="X",
            bpmn_process_identifier="x",
            completed=False,
            created_at_in_seconds=1000,
        )
    )
    db_session.flush()
    chain = workflow.list_human_tasks_for_instance(
        db_session, tenant_id=TENANT, process_instance_id=PI_ID
    )
    assert [row["name"] for row in chain] == ["Priya Nair"]


def _event(session, *, event_type, timestamp, user_id=None, task_guid=None):
    from m8flow_bpmn_core.models.process_instance_event import ProcessInstanceEventModel

    session.add(
        ProcessInstanceEventModel(
            m8f_tenant_id=TENANT,
            process_instance_id=PI_ID,
            event_type=event_type,
            timestamp=timestamp,
            user_id=user_id,
            task_guid=task_guid,
        )
    )
    session.flush()


def test_activity_events_ordering_actor_and_task_title(db_session):
    _user(db_session, uid=1, username="priya", display_name="Priya Nair")
    # A human task whose task_guid matches an event -> supplies task_title.
    _human_task(
        db_session,
        task_name="submit_claim",
        status="COMPLETED",
        completed=True,
        created_at=1000,
        completed_by_user_id=1,
        updated_at=1100,
    )
    from m8flow_bpmn_core.models.human_task import HumanTaskModel

    ht = db_session.query(HumanTaskModel).filter_by(task_name="submit_claim").first()
    ht.task_guid = "task-guid-1"
    ht.task_title = "Submit Expense Claim"
    db_session.flush()

    # System event (no user), then a user+task event; insert reversed.
    _event(db_session, event_type="task_completed", timestamp=1756000200.5, user_id=1, task_guid="task-guid-1")
    _event(db_session, event_type="process_instance_created", timestamp=1756000100.0)

    events = workflow.list_instance_events(
        db_session, tenant_id=TENANT, process_instance_id=PI_ID
    )
    assert events == [
        {
            "event_type": "process_instance_created",
            "actor_name": None,
            "timestamp": 1756000100.0,
            "task_guid": None,
            "task_title": None,
        },
        {
            "event_type": "task_completed",
            "actor_name": "Priya Nair",
            "timestamp": 1756000200.5,
            "task_guid": "task-guid-1",
            "task_title": "Submit Expense Claim",
        },
    ]


def test_activity_events_tenant_scoped(db_session):
    _event(db_session, event_type="process_instance_created", timestamp=1.0)
    from m8flow_bpmn_core.models.process_instance_event import ProcessInstanceEventModel

    db_session.add(
        ProcessInstanceEventModel(
            m8f_tenant_id="other-tenant",
            process_instance_id=PI_ID,
            event_type="process_instance_completed",
            timestamp=2.0,
        )
    )
    db_session.flush()
    events = workflow.list_instance_events(
        db_session, tenant_id=TENANT, process_instance_id=PI_ID
    )
    assert [e["event_type"] for e in events] == ["process_instance_created"]


def test_designer_events_join_task_definition_not_human_task(db_session):
    import uuid

    from m8flow_bpmn_core.models.bpmn_process import BpmnProcessModel
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.human_task import HumanTaskModel
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel

    _user(db_session, uid=1, username="priya", display_name="Priya Nair")
    definition = BpmnProcessDefinitionModel(
        m8f_tenant_id=TENANT,
        single_process_hash=uuid.uuid4().hex,
        bpmn_identifier="Process_approval",
        properties_json={},
    )
    db_session.add(definition)
    db_session.flush()
    bpmn_process = BpmnProcessModel(
        m8f_tenant_id=TENANT,
        bpmn_process_definition_id=definition.id,
        properties_json={},
        json_data_hash=uuid.uuid4().hex,
    )
    db_session.add(bpmn_process)
    db_session.flush()
    task_def = TaskDefinitionModel(
        m8f_tenant_id=TENANT,
        bpmn_process_definition_id=definition.id,
        bpmn_identifier="Event_0jqbb0y",
        bpmn_name=None,
        typename="StartEvent",
        properties_json={},
    )
    db_session.add(task_def)
    db_session.flush()
    guid = str(uuid.uuid4())
    db_session.add(
        TaskModel(
            m8f_tenant_id=TENANT,
            guid=guid,
            bpmn_process_id=bpmn_process.id,
            process_instance_id=PI_ID,
            task_definition_id=task_def.id,
            state="COMPLETED",
            properties_json={},
            json_data_hash=uuid.uuid4().hex,
            python_env_data_hash=uuid.uuid4().hex,
        )
    )
    db_session.add(
        HumanTaskModel(
            m8f_tenant_id=TENANT,
            process_instance_id=PI_ID,
            task_guid=guid,
            task_name="submit_claim",
            task_title="Submit Expense Claim",
            task_type="UserTask",
            task_status="COMPLETED",
            process_model_display_name="Approval",
            bpmn_process_identifier="human-task-process-id",
            completed=True,
            created_at_in_seconds=1000,
        )
    )
    _event(db_session, event_type="task_completed", timestamp=2.0, user_id=1, task_guid=guid)
    _event(db_session, event_type="process_instance_created", timestamp=1.0)

    rows = workflow.list_instance_events_for_designer(
        db_session, tenant_id=TENANT, process_instance_id=PI_ID
    )
    assert [r["event_type"] for r in rows] == [
        "process_instance_created",
        "task_completed",
    ]
    assert rows[0]["user"] == "system"
    assert rows[0]["bpmn_process"] is None
    assert rows[1]["user"] == "Priya Nair"
    assert rows[1]["bpmn_process"] == "Process_approval"
    assert rows[1]["task_name"] is None
    assert rows[1]["task_identifier"] == "Event_0jqbb0y"
    assert rows[1]["task_type"] == "StartEvent"
    assert isinstance(rows[1]["id"], int)
    assert "task_title" not in rows[1]


def test_designer_events_tenant_scoped(db_session):
    _event(db_session, event_type="process_instance_created", timestamp=1.0)
    from m8flow_bpmn_core.models.process_instance_event import ProcessInstanceEventModel

    db_session.add(
        ProcessInstanceEventModel(
            m8f_tenant_id="other-tenant",
            process_instance_id=PI_ID,
            event_type="process_instance_completed",
            timestamp=2.0,
        )
    )
    db_session.flush()
    rows = workflow.list_instance_events_for_designer(
        db_session, tenant_id=TENANT, process_instance_id=PI_ID
    )
    assert [r["event_type"] for r in rows] == ["process_instance_created"]


def test_designer_milestones_one_row_or_empty(db_session):
    import uuid

    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    _user(db_session, uid=1, username="priya", display_name="Priya Nair")
    definition = BpmnProcessDefinitionModel(
        m8f_tenant_id=TENANT,
        single_process_hash=uuid.uuid4().hex,
        bpmn_identifier="Process_approval",
        properties_json={},
    )
    db_session.add(definition)
    db_session.flush()
    instance = ProcessInstanceModel(
        m8f_tenant_id=TENANT,
        process_model_identifier="finance/approval",
        process_model_display_name="Approval",
        process_initiator_id=1,
        bpmn_process_definition_id=definition.id,
        status="waiting",
        start_in_seconds=1756000100,
        created_at_in_seconds=1756000100,
        updated_at_in_seconds=1756000100,
        last_milestone_bpmn_name="Approval",
    )
    db_session.add(instance)
    db_session.flush()

    rows = workflow.list_instance_milestones_for_designer(
        db_session, tenant_id=TENANT, process_instance_id=instance.id
    )
    assert rows == [
        {
            "milestone": "Approval",
            "bpmn_process": "Process_approval",
            "timestamp": 1756000100,
        }
    ]

    instance.last_milestone_bpmn_name = None
    db_session.flush()
    assert (
        workflow.list_instance_milestones_for_designer(
            db_session, tenant_id=TENANT, process_instance_id=instance.id
        )
        == []
    )


def test_completable_tasks_candidates_only_not_approval_chain(db_session):
    from m8flow_bpmn_core.models.human_task_user import HumanTaskUserModel

    _user(db_session, uid=1, username="priya", display_name="Priya Nair")
    _user(db_session, uid=2, username="manager", display_name="Asha")

    mine = _human_task(
        db_session,
        task_name="submit_claim",
        status="READY",
        completed=False,
        created_at=1000,
        actual_owner_id=1,
        lane_name="Submitter",
    )
    mine.task_title = "Submit Expense Claim"
    theirs = _human_task(
        db_session,
        task_name="manager_review",
        status="READY",
        completed=False,
        created_at=2000,
        actual_owner_id=2,
        lane_name="Manager",
    )
    theirs.task_title = "Manager Review"
    done = _human_task(
        db_session,
        task_name="done_step",
        status="COMPLETED",
        completed=True,
        created_at=500,
        actual_owner_id=1,
        updated_at=600,
    )
    done.task_title = "Already done"
    db_session.add(
        HumanTaskUserModel(m8f_tenant_id=TENANT, human_task_id=mine.id, user_id=1)
    )
    db_session.add(
        HumanTaskUserModel(m8f_tenant_id=TENANT, human_task_id=theirs.id, user_id=2)
    )
    db_session.add(
        HumanTaskUserModel(m8f_tenant_id=TENANT, human_task_id=done.id, user_id=1)
    )
    db_session.flush()

    rows = workflow.list_completable_tasks_for_designer(
        db_session, tenant_id=TENANT, process_instance_id=PI_ID, user_id=1
    )
    assert rows == [
        {
            "id": mine.id,
            "task_title": "Submit Expense Claim",
            "task_name": "submit_claim",
            "lane_name": "Submitter",
        }
    ]
    assert "name" not in rows[0]


def test_completed_tasks_splits_mine_and_all_uses_title_not_owner_name(db_session):
    from m8flow_bpmn_core.models.human_task_user import HumanTaskUserModel

    _user(db_session, uid=1, username="priya", display_name="Priya Nair")
    _user(db_session, uid=2, username="manager", display_name="Asha")

    mine = _human_task(
        db_session,
        task_name="submit_claim",
        status="COMPLETED",
        completed=True,
        created_at=1000,
        actual_owner_id=1,
        completed_by_user_id=1,
        updated_at=1100,
    )
    mine.task_title = "Submit Expense Claim"
    theirs = _human_task(
        db_session,
        task_name="manager_review",
        status="COMPLETED",
        completed=True,
        created_at=2000,
        actual_owner_id=2,
        completed_by_user_id=2,
        updated_at=2100,
    )
    theirs.task_title = None
    incomplete = _human_task(
        db_session,
        task_name="still_open",
        status="READY",
        completed=False,
        created_at=3000,
        actual_owner_id=1,
    )
    incomplete.task_title = "Still open"
    db_session.add(
        HumanTaskUserModel(m8f_tenant_id=TENANT, human_task_id=mine.id, user_id=1)
    )
    db_session.add(
        HumanTaskUserModel(m8f_tenant_id=TENANT, human_task_id=theirs.id, user_id=2)
    )
    db_session.add(
        HumanTaskUserModel(m8f_tenant_id=TENANT, human_task_id=incomplete.id, user_id=1)
    )
    db_session.flush()

    payload = workflow.list_completed_tasks_for_designer(
        db_session, tenant_id=TENANT, process_instance_id=PI_ID, user_id=1
    )
    assert payload["completed_by_me"] == [
        {
            "id": mine.id,
            "task_title": "Submit Expense Claim",
            "task_name": "submit_claim",
            "completed_by": "Priya Nair",
            "timestamp": 1100,
        }
    ]
    assert payload["all_completed"] == [
        {
            "id": mine.id,
            "task_title": "Submit Expense Claim",
            "task_name": "submit_claim",
            "completed_by": "Priya Nair",
            "timestamp": 1100,
        },
        {
            "id": theirs.id,
            "task_title": None,
            "task_name": "manager_review",
            "completed_by": "Asha",
            "timestamp": 2100,
        },
    ]
    assert "name" not in payload["all_completed"][0]
    assert payload["all_completed"][0]["completed_by"] != "submit_claim"
