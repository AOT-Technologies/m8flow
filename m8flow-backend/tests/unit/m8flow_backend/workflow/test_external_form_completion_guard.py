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
    from m8flow_bpmn_core.models.human_task import HumanTaskModel

    task = HumanTaskModel(
        m8f_tenant_id=tenant_id,
        process_instance_id=PI_ID,
        task_id="task-guid-1",
        task_name=task_name,
        task_title=task_name,
        task_type="UserTask",
        task_status="ready",
        process_model_display_name="Callback request",
        bpmn_process_identifier="test-group/callback-request",
        completed=False,
        created_at=datetime.fromtimestamp(1, timezone.utc),
        json_metadata=json_metadata,
    )
    session.add(task)
    session.flush()
    return task


def _guard(session, task):
    workflow._reject_in_app_completion_of_external_form_task(
        session, tenant_id=task.m8f_tenant_id, human_task_id=task.id
    )


def _link(session, task, *, status="pending", expires_at_in_seconds=None, tenant_id=None):
    """A secure-link row for `task`, as ExternalFormService.create_requests_for_task writes it."""
    from m8flow_backend.models.external_form_request import ExternalFormRequestModel

    session.add(
        ExternalFormRequestModel(
            m8f_tenant_id=tenant_id or task.m8f_tenant_id,
            reference_id=f"ref-{task.id}-{status}",
            process_instance_id=task.process_instance_id,
            task_guid=task.task_id,
            recipient_user_id=1,
            email="recipient@example.test",
            external_form_url="https://forms.example/f1",
            status=status,
            expires_at_in_seconds=expires_at_in_seconds,
            attempts=0,
        )
    )
    session.flush()


def test_blocks_in_app_completion_of_an_external_form_task(app, db_session):
    task = _human_task(db_session, json_metadata=EXTERNAL_FORM_METADATA)
    _link(db_session, task)

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
            db_session, tenant_id=TENANT, human_task_id=task.id
        )  # must not raise


def test_blocks_outside_a_request_context(app, db_session):
    """No request means no flag, so a background caller is never the external path."""
    task = _human_task(db_session, json_metadata=EXTERNAL_FORM_METADATA)
    _link(db_session, task)

    with app.app_context():
        with pytest.raises(ApiError) as caught:
            _guard(db_session, task)

    assert caught.value.error_code == "external_form_task_not_completable_in_app"


@pytest.mark.parametrize("link_status", [None, "expired"])
def test_allows_in_app_completion_without_an_open_link(app, db_session, link_status):
    """M8F-574: an assignee with no email is never sent a link, and an expired link can no
    longer be used. Blocking either case would strand the task with no way to finish it."""
    task = _human_task(db_session, json_metadata=EXTERNAL_FORM_METADATA)
    if link_status:
        _link(db_session, task, status=link_status)

    with app.test_request_context("/"):
        _guard(db_session, task)  # must not raise


def test_allows_in_app_completion_once_the_link_is_past_its_expiry(app, db_session):
    """A link keeps its open status until someone opens it after expiry, so the guard
    compares the time itself."""
    task = _human_task(db_session, json_metadata=EXTERNAL_FORM_METADATA)
    _link(db_session, task, status="notified", expires_at_in_seconds=1)

    with app.test_request_context("/"):
        _guard(db_session, task)  # must not raise


def test_a_link_in_another_tenant_does_not_block(app, db_session):
    """Instance ids are only unique per tenant, so another tenant's link is not this task's."""
    task = _human_task(db_session, json_metadata=EXTERNAL_FORM_METADATA)
    _link(db_session, task, tenant_id=OTHER_TENANT)

    with app.test_request_context("/"):
        _guard(db_session, task)  # must not raise
