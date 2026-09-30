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


def test_submit_completes_as_recipient_past_the_real_external_form_guard(db_session, monkeypatch):
    """The flag `submit()` sets must satisfy the real `workflow` guard (a mismatch 409s
    every link), and `g.user` must stay unset (Postgres RLS would lazy-load its groups
    mid-connection; SQLite never runs that hook)."""
    from m8flow_backend import workflow
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
            json_metadata={
                "task_definition_properties": {
                    "extensions": {"properties": {"externalFormUrl": "https://forms.example/task-guid-1"}}
                }
            },
        )
    )
    db_session.commit()

    seen = {}

    def _complete(session, **kwargs):
        workflow._reject_in_app_completion_of_external_form_task(
            session, tenant_id=kwargs["tenant_id"], human_task_id=kwargs["human_task_id"]
        )
        seen.update(kwargs, g_user=getattr(g, "user", None))

    monkeypatch.setattr("m8flow_backend.human_task.submit_external_form", _complete)

    ExternalFormService.submit(row.reference_id, {"answer": "x"})

    assert seen["user_id"] == user.id
    assert seen["g_user"] is None
    db_session.refresh(row)
    assert row.status == ExternalFormRequestStatus.completed.value


# ---------------------------------------------------------------------------
# Producer: ready external-form tasks -> tracking rows + NATS event
#
# The producer that turns a ready `externalFormUrl` user task into tracking rows
# was lost with the retired Spiff patch registry, which left the notification
# worker permanently idle (empty table, no event) and no email ever sent. These
# tests pin the re-homed host producer. Human tasks are stubs: the producer only
# reads `json_metadata` and `potential_owners` off the committed row, so a fake
# read session keeps this away from the core fixture graph.
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter_by(self, **kwargs):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Read side of the producer only; writes still go through `db.session`."""

    def __init__(self, rows, tenant=None):
        self._rows = rows
        self._tenant = tenant

    def query(self, _model):
        return _FakeQuery(self._rows)

    def get(self, _model, _pk):
        return self._tenant


class _StubOwner:
    def __init__(self, user_id, email, username):
        self.id = user_id
        self.email = email
        self.username = username


class _StubHumanTask:
    def __init__(self, task_guid, external_form_url, owners):
        self.task_guid = task_guid
        self.potential_owners = owners
        properties = {"externalFormUrl": external_form_url} if external_form_url else {}
        self.json_metadata = {
            "task_definition_properties": {"extensions": {"properties": properties}}
        }


def _rows_for(db_session, task_guid):
    from m8flow_backend.models.external_form_request import ExternalFormRequestModel

    return (
        db_session.query(ExternalFormRequestModel)
        .filter_by(task_guid=task_guid)
        .all()
    )


def test_emit_requests_for_ready_tasks_creates_a_row_per_recipient(db_session):
    task = _StubHumanTask(
        "task-guid-ready",
        "https://forms.example/f1",
        [_StubOwner(1, "a@example.com", "a"), _StubOwner(2, "b@example.com", "b")],
    )

    ExternalFormService.emit_requests_for_ready_tasks(
        _FakeSession([task]), tenant_id="t1", process_instance_id=77
    )

    rows = _rows_for(db_session, "task-guid-ready")
    assert sorted(row.email for row in rows) == ["a@example.com", "b@example.com"]
    assert {row.external_form_url for row in rows} == {"https://forms.example/f1"}
    assert {row.status for row in rows} == {ExternalFormRequestStatus.pending.value}


def test_emit_requests_for_ready_tasks_ignores_tasks_without_the_extension(db_session):
    task = _StubHumanTask("task-guid-plain", None, [_StubOwner(1, "a@example.com", "a")])

    ExternalFormService.emit_requests_for_ready_tasks(
        _FakeSession([task]), tenant_id="t1", process_instance_id=78
    )

    assert _rows_for(db_session, "task-guid-plain") == []


def test_emit_requests_for_ready_tasks_skips_recipients_without_an_email(db_session):
    task = _StubHumanTask(
        "task-guid-no-email", "https://forms.example/f1", [_StubOwner(1, "", "no-email")]
    )

    ExternalFormService.emit_requests_for_ready_tasks(
        _FakeSession([task]), tenant_id="t1", process_instance_id=79
    )

    assert _rows_for(db_session, "task-guid-no-email") == []


def test_emit_requests_for_ready_tasks_is_idempotent(db_session):
    task = _StubHumanTask(
        "task-guid-twice", "https://forms.example/f1", [_StubOwner(1, "a@example.com", "a")]
    )
    session = _FakeSession([task])

    ExternalFormService.emit_requests_for_ready_tasks(
        session, tenant_id="t1", process_instance_id=80
    )
    ExternalFormService.emit_requests_for_ready_tasks(
        session, tenant_id="t1", process_instance_id=80
    )

    assert len(_rows_for(db_session, "task-guid-twice")) == 1


def test_emit_requests_for_ready_tasks_publishes_the_fast_path_event(db_session, monkeypatch):
    from m8flow_backend.services.nats_service import NatsService

    published: list[tuple[str, dict]] = []
    monkeypatch.setattr("m8flow_backend.config.nats_enabled", lambda: True)
    monkeypatch.setattr(
        NatsService,
        "publish_notification",
        classmethod(lambda cls, slug, payload: published.append((slug, payload))),
    )

    class _StubTenant:
        slug = "acme"

    task = _StubHumanTask(
        "task-guid-published", "https://forms.example/f1", [_StubOwner(1, "a@example.com", "a")]
    )

    ExternalFormService.emit_requests_for_ready_tasks(
        _FakeSession([task], tenant=_StubTenant()), tenant_id="t1", process_instance_id=81
    )

    assert len(published) == 1
    slug, payload = published[0]
    assert slug == "acme"
    assert payload["event_type"] == "external_form.requests_created"
    assert payload["tenant_id"] == "t1"
    assert payload["process_instance_id"] == 81
    assert payload["task_guid"] == "task-guid-published"
    assert payload["reference_ids"] == [_rows_for(db_session, "task-guid-published")[0].reference_id]


# ---------------------------------------------------------------------------
# Open vs actionable. A failed send and a request parked for missing SMTP are not
# submittable, but they are still the live request for their (task, recipient)
# pair -- so they must suppress a duplicate row, and a parked link must never be
# accepted, because it was never delivered to anyone.
# ---------------------------------------------------------------------------


def _set_status(db_session, row, status, **fields):
    row.status = status
    for name, value in fields.items():
        setattr(row, name, value)
    db_session.commit()


def test_a_failed_request_does_not_produce_a_duplicate(db_session):
    [row] = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=500,
        task_guid="task-guid-open",
        external_form_url="https://forms.example/f1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
    )
    _set_status(db_session, row, ExternalFormRequestStatus.failed.value)

    again = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=500,
        task_guid="task-guid-open",
        external_form_url="https://forms.example/f1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
    )

    assert again == []


def test_a_parked_request_does_not_produce_a_duplicate(db_session):
    [row] = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=501,
        task_guid="task-guid-parked",
        external_form_url="https://forms.example/f1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
    )
    _set_status(db_session, row, ExternalFormRequestStatus.smtp_unconfigured.value)

    again = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=501,
        task_guid="task-guid-parked",
        external_form_url="https://forms.example/f1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
    )

    assert again == []


def test_a_failed_send_leaves_the_link_usable(db_session):
    """The recipient may already hold this link; a delivery/resume failure is not
    their fault and must not brick it."""
    [row] = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=502,
        task_guid="task-guid-failed",
        external_form_url="https://forms.example/f1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
    )
    _set_status(db_session, row, ExternalFormRequestStatus.failed.value)

    context = ExternalFormService.get_form_context(row.reference_id)

    assert context["actionable"] is True


def test_a_parked_link_is_refused(db_session):
    """Nobody can legitimately hold this link -- it was never emailed -- so accepting it
    would let whoever read the database submit the form as the recipient."""
    [row] = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=503,
        task_guid="task-guid-refused",
        external_form_url="https://forms.example/f1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
    )
    _set_status(db_session, row, ExternalFormRequestStatus.smtp_unconfigured.value)

    context = ExternalFormService.get_form_context(row.reference_id)
    assert context["actionable"] is False

    with pytest.raises(ApiError) as caught:
        ExternalFormService.submit(row.reference_id, {"field": "value"})

    assert caught.value.error_code == "reference_not_active"
    assert caught.value.status_code == 409


def test_a_parked_request_still_expires_by_ttl(db_session):
    [row] = ExternalFormService.create_requests_for_task(
        tenant_id="t1",
        process_instance_id=504,
        task_guid="task-guid-ttl",
        external_form_url="https://forms.example/f1",
        recipients=[{"user_id": 1, "email": "a@example.com"}],
        expires_at_in_seconds=1,
    )
    _set_status(db_session, row, ExternalFormRequestStatus.smtp_unconfigured.value)

    ExternalFormService.get_form_context(row.reference_id)

    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.expired.value
