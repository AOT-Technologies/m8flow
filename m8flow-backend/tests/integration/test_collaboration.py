# SPDX-License-Identifier: Apache-2.0
"""Run modeled collaboration messages through the host under tenant RLS."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from m8flow_core import api
from m8flow_core.models.process_instance import ProcessInstanceModel

from .support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = [
    pytest.mark.usefixtures("host_db"),
    pytest.mark.skipif(
        not hasattr(api.InitializeProcessInstanceFromDefinitionCommand, "collaboration_correlation_key"),
        reason="requires a collaboration-capable core wheel",
    ),
]


@pytest.mark.parametrize("message_start", [True, False], ids=["message-start", "message-catch"])
def test_order_and_fulfilment_share_one_model(message_start):
    from m8flow_backend import workflow

    tenant = new_tenant_id("collaboration")
    model = "orders/collaboration"
    key = "order-123"
    with tenant_session(tenant) as session:
        user = provision_member(session, tenant_id=tenant, role="editor")
        user_id = user.id
        save_model(
            session, tenant_id=tenant, user_id=user_id, path=model,
            fixture="order-fulfilment-collaboration.bpmn",
        )

    def start(process_id):
        with tenant_session(tenant) as session:
            return workflow.start(
                session, tenant_id=tenant, user_id=user_id, process_model_identifier=model,
                bpmn_process_id=process_id, collaboration_correlation_key=key,
                submission_metadata={"start_fulfilment": message_start},
            ).id

    def finish_task(instance_id):
        with tenant_session(tenant) as session:
            item = next(
                item for item in workflow.list_pending_tasks(session, tenant_id=tenant, user_id=user_id)
                if item.process_instance_id == instance_id
            )
            workflow.claim(session, tenant_id=tenant, work_item_id=item.id, user_id=user_id)
            workflow.complete(session, tenant_id=tenant, work_item_id=item.id, user_id=user_id)

    if not message_start:
        finish_task(start("Fulfilment"))
    order_id = start("Order")
    finish_task(order_id)

    with tenant_session(tenant) as session:
        assert workflow.run_due(session, tenant_id=tenant, now=datetime.now(UTC)) == 1
    with tenant_session(tenant) as session:
        instances = list(session.scalars(select(ProcessInstanceModel)))
        assert len(instances) == 2
        assert {instance.status for instance in instances} == {"complete"}
        assert {instance.collaboration_correlation_key for instance in instances} == {key}
        assert len({instance.bpmn_process_definition_id for instance in instances}) == 1
        detail = workflow.get_instance_detail_for_designer(session, tenant_id=tenant, process_instance_id=order_id)
        assert "ApproveOrder" in {task["bpmn_identifier"] for task in detail["tasks"]}
        diagram = workflow.diagram_only_bpmn_xml(detail["bpmn_xml"])
        assert 'xmlns:orders="urn:m8flow:orders"' in diagram
        assert workflow.run_due(session, tenant_id=tenant, now=datetime.now(UTC)) == 0
