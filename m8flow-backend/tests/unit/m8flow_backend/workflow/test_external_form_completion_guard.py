"""An external-form task is completed by its emailed link and by nothing else.

The point of an external-form task is that a specific recipient completes it through a
per-recipient secure link. Nothing stopped the in-app task page from completing it on
their behalf, which strands the tracking row and defeats the link entirely. The guard
lives in `workflow.complete` -- the single choke point every completion route funnels
through -- and recognises the legitimate path by the flag `ExternalFormService.submit`
sets on the request.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from flask import g

from m8flow_backend import workflow
from m8flow_backend.errors import ApiError
from m8flow_backend.workflow import EXTERNAL_FORM_COMPLETION_FLAG

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"
PI_ID = 900

EXTERNAL_FORM_METADATA = {
    "task_definition_properties": {
        "extensions": {"properties": {"externalFormUrl": "https://forms.example/f1"}}
    }
}


def _human_task(session, *, task_name="Activity_1", json_metadata=None, tenant_id=TENANT):
    import uuid

    from m8flow_bpmn_core.models.bpmn_process import BpmnProcessModel
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel
    from m8flow_bpmn_core.models.work_item import WorkItemModel

    properties = (json_metadata or {}).get("task_definition_properties", {})
    definition = BpmnProcessDefinitionModel(
        m8f_tenant_id=tenant_id,
        process_xml_digest=uuid.uuid4().hex,
        bpmn_identifier="test-group/callback-request",
        properties_json={},
    )
    session.add(definition)
    session.flush()
    session.add(
        ProcessInstanceModel(
            id=PI_ID,
            m8f_tenant_id=tenant_id,
            process_model_identifier="test-group/callback-request",
            process_model_display_name="Callback request",
            process_initiator_id=1,
            bpmn_process_definition_id=definition.id,
            status="user_input_required",
        )
    )
    process = BpmnProcessModel(
        m8f_tenant_id=tenant_id,
        bpmn_process_definition_id=definition.id,
        properties_json={},
        json_data_hash=uuid.uuid4().hex,
    )
    session.add(process)
    session.flush()
    task_definition = TaskDefinitionModel(
        m8f_tenant_id=tenant_id,
        bpmn_process_definition_id=definition.id,
        bpmn_identifier=task_name,
        bpmn_name=task_name,
        typename="UserTask",
        properties_json=properties,
    )
    session.add(task_definition)
    session.flush()
    guid = str(uuid.uuid4())
    session.add(
        TaskModel(
            m8f_tenant_id=tenant_id,
            guid=guid,
            bpmn_process_id=process.id,
            process_instance_id=PI_ID,
            task_definition_id=task_definition.id,
            state="READY",
            properties_json={},
            json_data_hash=uuid.uuid4().hex,
            python_env_data_hash=uuid.uuid4().hex,
        )
    )
    session.flush()
    task = WorkItemModel(
        m8f_tenant_id=tenant_id,
        process_instance_id=PI_ID,
        task_guid=guid,
        task_status="ready",
        completed=False,
        created_at=datetime.fromtimestamp(1, timezone.utc),
    )
    session.add(task)
    session.flush()
    return task


def _guard(session, task):
    workflow._reject_in_app_completion_of_external_form_task(
        session, tenant_id=task.m8f_tenant_id, work_item_id=task.id
    )


def test_blocks_in_app_completion_of_an_external_form_task(app, db_session):
    task = _human_task(db_session, json_metadata=EXTERNAL_FORM_METADATA)

    with app.test_request_context("/"):
        with pytest.raises(ApiError) as caught:
            _guard(db_session, task)

    assert caught.value.error_code == "external_form_task_not_completable_in_app"
    assert caught.value.status_code == 409


def test_allows_the_external_form_submission_path(app, db_session):
    """ExternalFormService.submit sets the flag before completing the task."""
    task = _human_task(db_session, json_metadata=EXTERNAL_FORM_METADATA)

    with app.test_request_context("/"):
        setattr(g, EXTERNAL_FORM_COMPLETION_FLAG, True)
        _guard(db_session, task)  # must not raise


def test_allows_an_ordinary_user_task(app, db_session):
    task = _human_task(db_session, json_metadata={"task_definition_properties": {"extensions": {}}})

    with app.test_request_context("/"):
        _guard(db_session, task)  # must not raise


def test_allows_a_task_with_no_task_definition_metadata(app, db_session):
    """Fails open: an unreadable definition has no externalFormUrl to enforce."""
    task = _human_task(db_session, json_metadata=None)

    with app.test_request_context("/"):
        _guard(db_session, task)  # must not raise


def test_ignores_a_task_belonging_to_another_tenant(app, db_session):
    """Tenant mismatch is not this guard's error to raise -- the core command rejects it."""
    task = _human_task(db_session, json_metadata=EXTERNAL_FORM_METADATA, tenant_id=OTHER_TENANT)

    with app.test_request_context("/"):
        workflow._reject_in_app_completion_of_external_form_task(
            db_session, tenant_id=TENANT, work_item_id=task.id
        )  # must not raise


def test_blocks_outside_a_request_context(app, db_session):
    """No request means no flag, so a background caller is never the external path."""
    task = _human_task(db_session, json_metadata=EXTERNAL_FORM_METADATA)

    with app.app_context():
        with pytest.raises(ApiError) as caught:
            _guard(db_session, task)

    assert caught.value.error_code == "external_form_task_not_completable_in_app"
