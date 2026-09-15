"""Regression coverage for architecture review finding W1: ExternalFormService
was wired to models.native.ExternalFormRequestModel, a legacy definition
targeting the wrong (unmigrated, singular-named) table with a completely
different schema (token/human_task_id) than the real migrated table
(reference_id/task_guid/status/...). Any real usage raised AttributeError at
first touch of `.status`/`.task_guid`/etc; this file's own directory had zero
tests, so nothing caught it. models/external_form_request.py now defines the
model against the real table -- these tests exercise it end-to-end.

ExternalFormService reads/writes through `db.session` (m8flow_backend.db.db),
which resolves to `g.db_session` inside a request context -- so tests run
inside `app.test_request_context()` with `g.db_session` pinned to the shared
`db_session` fixture, the same way a real request would provide it.
"""

from __future__ import annotations

import pytest
from flask import g

from m8flow_backend.errors import ApiError
from m8flow_backend.models.external_form_request import ExternalFormRequestStatus
from m8flow_backend.services.external_form_service import ExternalFormService


@pytest.fixture(autouse=True)
def _bind_request_scoped_session(app, db_session):
    with app.test_request_context("/"):
        g.db_session = db_session
        yield


def test_create_requests_for_task_persists_with_the_real_schema(db_session):
    created = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=123,
        task_guid="task-guid-1",
        external_form_url="https://forms.example/task-guid-1",
        recipients=[{"user_id": 1, "email": "a@example.com", "user_details": {"name": "A"}}],
    )
    assert len(created) == 1
    row = created[0]
    assert row.id is not None
    assert row.status == ExternalFormRequestStatus.pending.value
    assert row.is_actionable() is True
    assert row.attempts == 0


def test_create_requests_for_task_skips_recipients_with_an_actionable_link(db_session):
    first = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=123,
        task_guid="task-guid-1",
        external_form_url="https://forms.example/task-guid-1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
    )
    second = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=123,
        task_guid="task-guid-1",
        external_form_url="https://forms.example/task-guid-1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
    )
    assert len(first) == 1
    assert second == []


def test_get_form_context_reports_status_and_actionability(db_session):
    [row] = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=123,
        task_guid="task-guid-1",
        external_form_url="https://forms.example/task-guid-1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
    )

    context = ExternalFormService.get_form_context(row.reference_id)

    assert context["reference_id"] == row.reference_id
    assert context["status"] == ExternalFormRequestStatus.pending.value
    assert context["actionable"] is True
    assert context["external_form_url"] == "https://forms.example/task-guid-1"
    # to_public_dict must not leak internal-only fields.
    assert "attempts" not in context
    assert "user_details" not in context
    assert "form_submission_data" not in context


def test_get_form_context_unknown_reference_id_is_404(db_session):
    with pytest.raises(ApiError) as excinfo:
        ExternalFormService.get_form_context("does-not-exist")
    assert excinfo.value.status_code == 404


def test_expired_request_reports_not_actionable(db_session):
    [row] = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=123,
        task_guid="task-guid-1",
        external_form_url="https://forms.example/task-guid-1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
        expires_at_in_seconds=1,  # already in the past
    )

    context = ExternalFormService.get_form_context(row.reference_id)

    assert context["status"] == ExternalFormRequestStatus.expired.value
    assert context["actionable"] is False


def _seed_recipient(db_session, *, user_id: int = 1):
    from m8flow_bpmn_core.models.user import UserModel

    user = UserModel(
        id=user_id,
        username=f"user-{user_id}",
        email=f"user-{user_id}@example.com",
        service="https://example.test/realms/m8flow",
        service_id=f"user-{user_id}",
        display_name=f"User {user_id}",
        created_at_in_seconds=0,
        updated_at_in_seconds=0,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_submit_workflow_failure_does_not_leave_link_as_submitted(db_session, monkeypatch):
    """Crash/failure after receiving the form must not consume the link as
    ``submitted`` (non-actionable, non-retryable) while the human task is still
    open — that used to happen via an intermediate commit before resume."""
    from m8flow_bpmn_core.models.human_task import HumanTaskModel

    user = _seed_recipient(db_session)
    [row] = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=123,
        task_guid="task-guid-1",
        external_form_url="https://forms.example/task-guid-1",
        recipients=[{"user_id": user.id, "email": user.email}],
    )
    db_session.add(
        HumanTaskModel(
            id=9001,
            m8f_tenant_id="t1",
            process_instance_id=123,
            task_id="task-guid-1",
            task_name="ExternalForm",
            task_title="Fill form",
            task_type="UserTask",
            task_status="READY",
            process_model_display_name="Demo",
            bpmn_process_identifier="demo/external",
            completed=False,
        )
    )
    db_session.commit()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated crash during workflow resume")

    monkeypatch.setattr(
        "m8flow_backend.human_task.submit_external_form",
        _boom,
    )

    with pytest.raises(ApiError) as excinfo:
        ExternalFormService.submit(row.reference_id, {"answer": "x"})
    assert excinfo.value.error_code == "workflow_resume_failed"

    db_session.refresh(row)
    assert row.status == ExternalFormRequestStatus.failed.value
    assert row.status != ExternalFormRequestStatus.submitted.value

    # Retry must not be rejected as already_submitted (would leave the workflow stuck).
    with pytest.raises(ApiError) as retry_exc:
        ExternalFormService.submit(row.reference_id, {"answer": "x"})
    assert retry_exc.value.error_code == "workflow_resume_failed"


def test_submit_not_found_records_failure_not_completed(db_session):
    """A missing human task is a retryable failure, not an already-completed terminal."""
    user = _seed_recipient(db_session)
    [row] = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=123,
        task_guid="missing-task",
        external_form_url="https://forms.example/missing",
        recipients=[{"user_id": user.id, "email": user.email}],
    )

    with pytest.raises(ApiError) as excinfo:
        ExternalFormService.submit(row.reference_id, {"answer": "x"})
    assert excinfo.value.error_code == "not_found"
    assert excinfo.value.status_code == 404

    db_session.refresh(row)
    assert row.status == ExternalFormRequestStatus.failed.value
