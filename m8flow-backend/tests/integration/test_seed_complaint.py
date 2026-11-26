"""All complaint signal paths run with the released core, real roles, and RLS."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from .support import new_tenant_id, provision_member, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")


@pytest.mark.parametrize("case_id", ["CMP-01", "CMP-02", "CMP-03", "CMP-04"])
def test_complaint_signal_paths_complete_with_released_core(case_id):
    from m8flow_core.models import ProcessInstanceModel
    from m8flow_core.models.task import TaskModel

    from m8flow_backend import workflow
    from m8flow_backend.catalog import versioned

    tenant = new_tenant_id("complaint")
    folder = Path(__file__).resolve().parents[3] / "m8flow-designer/e2e/seed/catalog/templates/customer-complaint"
    case = next(row for row in json.loads((folder / "paths.json").read_text())["paths"] if row["id"] == case_id)
    answers = deepcopy(case["answers"])
    files = {path.name: path.read_bytes() for path in folder.iterdir() if path.name != "paths.json"}
    model_id = "complaints/signals"
    with tenant_session(tenant) as session:
        editor = provision_member(session, tenant_id=tenant, role="editor")
        submitter = provision_member(session, tenant_id=tenant, role="submitter", lanes=("Submitters",))
        reviewer = provision_member(session, tenant_id=tenant, role="reviewer", lanes=("Approvers",))
        admin = provision_member(session, tenant_id=tenant, role="tenant-admin", lanes=("Administrators",))
        users = [submitter.id, reviewer.id, admin.id]
        model = versioned.create(session, tenant, model_id, name="Complaints", files=files)
        versioned.publish(session, model, user_id=editor.id, username=editor.username)
        instance_id = workflow.start(
            session, tenant_id=tenant, user_id=submitter.id, process_model_identifier=model_id,
        ).id

    for _ in range(20):
        with tenant_session(tenant) as session:
            instance = session.get(ProcessInstanceModel, instance_id)
            if instance.status == "complete":
                break
            ready = [
                (user_id, task.id, task.task_name.removesuffix(" [child]"))
                for user_id in users
                for task in workflow.list_pending_tasks(session, tenant_id=tenant, user_id=user_id)
                if task.process_instance_id == instance_id
            ]
            assert len(ready) == 1, (instance.status, ready)
            user_id, task_id, identifier = ready[0]
            payload = answers.get(identifier, {})
            if isinstance(payload, list):
                payload = payload.pop(0)
            workflow.claim(session, tenant_id=tenant, work_item_id=task_id, user_id=user_id)
            workflow.complete(session, tenant_id=tenant, work_item_id=task_id, user_id=user_id, task_payload=payload)

    with tenant_session(tenant) as session:
        assert session.get(ProcessInstanceModel, instance_id).status == "complete"
        completed = {
            task.task_definition.properties_json.get("__m8f_task_identifier", task.task_definition.bpmn_identifier)
            for task in session.scalars(select(TaskModel).where(
                TaskModel.process_instance_id == instance_id, TaskModel.state == "COMPLETED",
            ))
        }
        assert set(case.get("expect_completed", [])) <= completed
        assert not set(case.get("expect_not_reached", [])) & completed
