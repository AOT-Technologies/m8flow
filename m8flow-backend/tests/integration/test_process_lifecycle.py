"""Process lifecycle through the host modules on real core, Postgres, and RLS."""

from __future__ import annotations

import pytest

from .support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

MODEL = "invoices/approval"


def _publish_and_start(tenant_id: str, *, starter_role: str = "submitter"):
    from m8flow_backend import workflow

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        starter = (
            editor if starter_role == "editor" else provision_member(session, tenant_id=tenant_id, role=starter_role)
        )
        save_model(session, tenant_id=tenant_id, user_id=editor.id, path=MODEL, fixture="invoice_approval_poc.bpmn")
    with tenant_session(tenant_id) as session:
        instance = workflow.start(
            session, tenant_id=tenant_id, user_id=starter.id, process_model_identifier=MODEL
        )
        return editor.id, starter.id, instance.id


def test_submitter_starts_claims_and_completes_a_user_task_to_the_end():
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.process_instance_metadata import ProcessInstanceMetadataModel
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("lifecycle")
    _editor_id, submitter_id, instance_id = _publish_and_start(tenant_id)

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, instance_id)
        assert instance.status == "user_input_required"
        assert instance.process_initiator_id == submitter_id
        pending = workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=submitter_id)
        assert [task.process_instance_id for task in pending] == [instance_id]
        work_item_id = pending[0].id

    with tenant_session(tenant_id) as session:
        workflow.claim(session, tenant_id=tenant_id, work_item_id=work_item_id, user_id=submitter_id)
    with tenant_session(tenant_id) as session:
        work_item = session.get(WorkItemModel, work_item_id)
        assert (work_item.actual_owner_id, work_item.task_status) == (submitter_id, "CLAIMED")

    with tenant_session(tenant_id) as session:
        workflow.complete(
            session,
            tenant_id=tenant_id,
            work_item_id=work_item_id,
            user_id=submitter_id,
            task_payload={"approval_state": "approved"},
        )

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, instance_id)
        work_item = session.get(WorkItemModel, work_item_id)
        assert instance.status == "complete"
        assert (work_item.completed, work_item.completed_by_user_id, work_item.task_status) == (
            True,
            submitter_id,
            "COMPLETED",
        )
        metadata = {
            row.key: row.value
            for row in session.query(ProcessInstanceMetadataModel).filter_by(process_instance_id=instance_id)
        }
        assert metadata["approval_state"] == "approved"
        assert workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=submitter_id) == []


def _pending_work_item_id(tenant_id: str, user_id: int) -> int:
    from m8flow_backend import workflow

    with tenant_session(tenant_id) as session:
        pending = workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=user_id)
        assert len(pending) == 1
        return pending[0].id


def _status(tenant_id: str, instance_id: int) -> str:
    from m8flow_core.models.process_instance import ProcessInstanceModel

    with tenant_session(tenant_id) as session:
        return session.get(ProcessInstanceModel, instance_id).status


def test_editor_suspends_resumes_and_terminates_an_instance():
    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_id = new_tenant_id("control")
    editor_id, _starter_id, instance_id = _publish_and_start(tenant_id, starter_role="editor")
    ids = {"tenant_id": tenant_id, "process_instance_id": instance_id, "user_id": editor_id}

    work_item_id = _pending_work_item_id(tenant_id, editor_id)
    with tenant_session(tenant_id) as session:
        workflow.suspend_instance(session, **ids)
    assert _status(tenant_id, instance_id) == "suspended"

    with tenant_session(tenant_id) as session:
        # A suspended instance's tasks leave the inbox.
        assert workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=editor_id) == []
    with pytest.raises(ApiError) as suspended_claim:
        with tenant_session(tenant_id) as session:
            workflow.claim(session, tenant_id=tenant_id, work_item_id=work_item_id, user_id=editor_id)
    assert (suspended_claim.value.status_code, suspended_claim.value.error_code) == (409, "invalid_state")

    with tenant_session(tenant_id) as session:
        workflow.resume_instance(session, **ids)
    # Core reports a resumed instance as `running` until the engine next
    # advances it, even though it is waiting on the same human task.
    assert _status(tenant_id, instance_id) == "running"
    assert _pending_work_item_id(tenant_id, editor_id) == work_item_id

    with tenant_session(tenant_id) as session:
        workflow.terminate_instance(session, **ids)
    assert _status(tenant_id, instance_id) == "terminated"

    # Core treats terminating a terminated instance as a no-op.
    with tenant_session(tenant_id) as session:
        again = workflow.terminate_instance(session, **ids)
        assert (again.id, again.status) == (instance_id, "terminated")
    assert _status(tenant_id, instance_id) == "terminated"

    # A finished instance cannot be suspended again.
    with pytest.raises(ApiError) as finished:
        with tenant_session(tenant_id) as session:
            workflow.suspend_instance(session, **ids)
    assert (finished.value.status_code, finished.value.error_code) == (409, "invalid_state")


def test_complete_requires_a_claim_and_a_second_completion_is_rejected():
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_id = new_tenant_id("twice")
    _editor_id, submitter_id, instance_id = _publish_and_start(tenant_id)
    work_item_id = _pending_work_item_id(tenant_id, submitter_id)
    complete = {"tenant_id": tenant_id, "work_item_id": work_item_id, "user_id": submitter_id}

    with pytest.raises(ApiError) as unclaimed:
        with tenant_session(tenant_id) as session:
            workflow.complete(session, **complete, task_payload={"approval_state": "approved"})
    assert (unclaimed.value.status_code, unclaimed.value.error_code) == (409, "invalid_state")
    assert _status(tenant_id, instance_id) == "user_input_required"

    with tenant_session(tenant_id) as session:
        workflow.claim(session, tenant_id=tenant_id, work_item_id=work_item_id, user_id=submitter_id)
    with tenant_session(tenant_id) as session:
        workflow.complete(
            session,
            tenant_id=tenant_id,
            work_item_id=work_item_id,
            user_id=submitter_id,
            task_payload={"approval_state": "approved"},
        )

    with pytest.raises(ApiError) as second:
        with tenant_session(tenant_id) as session:
            workflow.complete(
                session,
                tenant_id=tenant_id,
                work_item_id=work_item_id,
                user_id=submitter_id,
                task_payload={"approval_state": "rejected"},
            )
    assert (second.value.status_code, second.value.error_code) == (409, "invalid_state")

    with tenant_session(tenant_id) as session:
        assert session.get(WorkItemModel, work_item_id).completed_by_user_id == submitter_id
    assert _status(tenant_id, instance_id) == "complete"
