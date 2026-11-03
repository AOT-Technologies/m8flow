"""Run the attached Dev multi-instance BPMN through the host and core runtime."""

from __future__ import annotations

import pytest

from .support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")


def test_uploaded_multi_instance_bpmn_runs_sequential_and_parallel_loops():
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("multi-instance")
    model_id = "bpmn-gap-tracker-tests/simple-multi-instance"
    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
        )

    with tenant_session(tenant_id) as session:
        started = workflow.start(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            process_model_identifier=model_id,
        )

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, started.id)
        assert instance is not None
        # The BPMN's final script task raises if either loop output differs.
        assert instance.status == "complete"
