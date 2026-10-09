"""Contract tests for the public external-form API routes.

These tests intentionally seed a ``WorkItemModel`` without relying on a legacy
human-task id.  The external-form request carries the runtime ``task_guid``;
the route/service must resolve that pair to the normalized work item before
submitting the form.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from m8flow_backend.identity import ensure_user
from m8flow_backend.models.external_form_request import ExternalFormRequestModel
from m8flow_backend.models.external_form_request import ExternalFormRequestStatus


def _seed_external_form_request(db_session):
    from m8flow_bpmn_core.models.work_item import WorkItemModel

    recipient = ensure_user(
        db_session,
        username="external-recipient",
        service="https://example.test/realms/m8flow",
        service_id="external-recipient",
    )
    task_guid = str(uuid4())
    work_item = WorkItemModel(
        m8f_tenant_id="t1",
        process_instance_id=321,
        task_guid=task_guid,
        task_status="READY",
        completed=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(work_item)
    db_session.flush()

    request = ExternalFormRequestModel(
        m8f_tenant_id="t1",
        reference_id="external-contract-reference",
        process_instance_id=work_item.process_instance_id,
        task_guid=task_guid,
        recipient_user_id=recipient.id,
        email="external-recipient@example.test",
        external_form_url="https://forms.example/external-contract-reference",
        status=ExternalFormRequestStatus.pending.value,
        attempts=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(request)
    db_session.commit()
    return request, work_item


def test_external_form_show_returns_contract_and_work_item_context(client, db_session):
    request, work_item = _seed_external_form_request(db_session)

    response = client.get(f"/v1.0/m8flow/external-forms/{request.reference_id}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["reference_id"] == request.reference_id
    assert body["status"] == ExternalFormRequestStatus.pending.value
    assert body["actionable"] is True
    assert body["process_instance_id"] == work_item.process_instance_id
    assert body["external_form_url"] == request.external_form_url


def test_external_form_submit_resolves_work_item_by_task_guid_and_preserves_contract(
    client, db_session, monkeypatch
):
    request, work_item = _seed_external_form_request(db_session)
    seen: dict[str, object] = {}

    def _submit(_session, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(process_instance_id=work_item.process_instance_id, status="complete")

    monkeypatch.setattr("m8flow_backend.human_task.submit_external_form", _submit)

    response = client.post(
        f"/v1.0/m8flow/external-forms/{request.reference_id}/submit",
        json={"data": {"answer": "approved"}},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["message"] == "Form submission accepted; the workflow has continued."
    assert body["data"] == {
        "reference_id": request.reference_id,
        "status": ExternalFormRequestStatus.completed.value,
        "process_instance_id": work_item.process_instance_id,
    }
    assert seen["work_item_id"] == work_item.id
    assert seen["user_id"] == request.recipient_user_id
    assert seen["task_payload"] == {"answer": "approved"}

    db_session.refresh(request)
    assert request.status == ExternalFormRequestStatus.completed.value
    assert request.form_submission_data == {"answer": "approved"}
