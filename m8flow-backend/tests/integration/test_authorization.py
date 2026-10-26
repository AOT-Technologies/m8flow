"""Core commands authorized by the host policy from real m8flow.yml grants.

Core decides every command through the policy the host installs at boot, so a
change in what core asks (command key, resource shape, permission) shows up
here as a role suddenly allowed or denied.
"""

from __future__ import annotations

import pytest

from tests.integration.support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

MODEL = "invoices/approval"


def _tenant_with_model(label: str, *roles: str):
    tenant_id = new_tenant_id(label)
    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        users = {role: provision_member(session, tenant_id=tenant_id, role=role).id for role in roles}
        save_model(session, tenant_id=tenant_id, user_id=editor.id, path=MODEL, fixture="invoice_approval_poc.bpmn")
    users["editor"] = editor.id
    return tenant_id, users


def _start(tenant_id: str, user_id: int) -> int:
    from m8flow_backend import workflow

    with tenant_session(tenant_id) as session:
        return workflow.start(
            session, tenant_id=tenant_id, user_id=user_id, process_model_identifier=MODEL
        ).id


def _instance_count(tenant_id: str) -> int:
    from m8flow_core.models.process_instance import ProcessInstanceModel

    with tenant_session(tenant_id) as session:
        return session.query(ProcessInstanceModel).filter_by(m8f_tenant_id=tenant_id).count()


@pytest.mark.parametrize("role", ["viewer", "reviewer"])
def test_roles_without_start_grant_cannot_start_a_process(role):
    from m8flow_backend.errors import ApiError

    tenant_id, users = _tenant_with_model(f"nostart-{role}", role)

    with pytest.raises(ApiError) as denied:
        _start(tenant_id, users[role])

    assert (denied.value.status_code, denied.value.error_code) == (403, "permission_denied")
    assert "process.start" in denied.value.message
    assert _instance_count(tenant_id) == 0


@pytest.mark.parametrize("operation", ["suspend_instance", "terminate_instance"])
def test_submitter_cannot_run_lifecycle_commands_editor_can(operation):
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_id, users = _tenant_with_model(f"lifecycle-{operation[:4]}", "submitter")
    instance_id = _start(tenant_id, users["submitter"])

    with pytest.raises(ApiError) as denied:
        with tenant_session(tenant_id) as session:
            getattr(workflow, operation)(
                session, tenant_id=tenant_id, process_instance_id=instance_id, user_id=users["submitter"]
            )
    assert (denied.value.status_code, denied.value.error_code) == (403, "permission_denied")

    with tenant_session(tenant_id) as session:
        assert session.get(ProcessInstanceModel, instance_id).status == "user_input_required"
        getattr(workflow, operation)(
            session, tenant_id=tenant_id, process_instance_id=instance_id, user_id=users["editor"]
        )
    with tenant_session(tenant_id) as session:
        assert session.get(ProcessInstanceModel, instance_id).status in {"suspended", "terminated"}


def test_viewer_cannot_claim_a_task_a_submitter_can():
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_id, users = _tenant_with_model("claim", "submitter", "viewer")
    _start(tenant_id, users["submitter"])
    with tenant_session(tenant_id) as session:
        (task,) = workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=users["submitter"])
        work_item_id = task.id

    with pytest.raises(ApiError) as denied:
        with tenant_session(tenant_id) as session:
            workflow.claim(session, tenant_id=tenant_id, work_item_id=work_item_id, user_id=users["viewer"])
    assert denied.value.status_code == 403

    with tenant_session(tenant_id) as session:
        assert session.get(WorkItemModel, work_item_id).actual_owner_id is None
        workflow.claim(session, tenant_id=tenant_id, work_item_id=work_item_id, user_id=users["submitter"])
    with tenant_session(tenant_id) as session:
        assert session.get(WorkItemModel, work_item_id).actual_owner_id == users["submitter"]
