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


MODEL = "orders/collaboration"
KEY = "order-123"


def _provision(tenant):
    with tenant_session(tenant) as session:
        user = provision_member(session, tenant_id=tenant, role="editor")
        save_model(
            session, tenant_id=tenant, user_id=user.id, path=MODEL,
            fixture="order-fulfilment-collaboration.bpmn",
        )
        return user.id


def _start(tenant, user_id, process_id, *, message_start):
    from m8flow_backend import workflow

    with tenant_session(tenant) as session:
        return workflow.start(
            session, tenant_id=tenant, user_id=user_id, process_model_identifier=MODEL,
            bpmn_process_id=process_id, collaboration_correlation_key=KEY,
            submission_metadata={"start_fulfilment": message_start},
        ).id


def _finish_task(tenant, user_id, instance_id):
    from m8flow_backend import workflow

    with tenant_session(tenant) as session:
        item = next(
            item for item in workflow.list_pending_tasks(session, tenant_id=tenant, user_id=user_id)
            if item.process_instance_id == instance_id
        )
        workflow.claim(session, tenant_id=tenant, work_item_id=item.id, user_id=user_id)
        workflow.complete(session, tenant_id=tenant, work_item_id=item.id, user_id=user_id)


@pytest.mark.parametrize("message_start", [True, False], ids=["message-start", "message-catch"])
def test_order_and_fulfilment_share_one_model(message_start):
    from m8flow_backend import workflow

    tenant = new_tenant_id("collaboration")
    user_id = _provision(tenant)
    if not message_start:
        receiver_id = _start(tenant, user_id, "Fulfilment", message_start=False)
        _finish_task(tenant, user_id, receiver_id)
    order_id = _start(tenant, user_id, "Order", message_start=message_start)
    _finish_task(tenant, user_id, order_id)

    with tenant_session(tenant) as session:
        assert workflow.run_due(session, tenant_id=tenant, now=datetime.now(UTC)) == 1
    with tenant_session(tenant) as session:
        instances = list(session.scalars(select(ProcessInstanceModel)))
        assert len(instances) == 2
        assert {instance.status for instance in instances} == {"complete"}
        assert {instance.collaboration_correlation_key for instance in instances} == {KEY}
        assert len({instance.bpmn_process_definition_id for instance in instances}) == 1
        detail = workflow.get_instance_detail_for_designer(session, tenant_id=tenant, process_instance_id=order_id)
        assert "ApproveOrder" in {task["bpmn_identifier"] for task in detail["tasks"]}
        diagram = workflow.diagram_only_bpmn_xml(detail["bpmn_xml"])
        assert 'xmlns:orders="urn:m8flow:orders"' in diagram
        assert workflow.run_due(session, tenant_id=tenant, now=datetime.now(UTC)) == 0


@pytest.mark.parametrize("message_start", [True, False], ids=["message-start", "message-catch"])
def test_collaboration_delivery_stays_in_the_sender_tenant(message_start):
    from m8flow_backend import workflow

    def setup(label):
        tenant = new_tenant_id(label)
        user_id = _provision(tenant)
        receiver_id = None
        if not message_start:
            receiver_id = _start(tenant, user_id, "Fulfilment", message_start=False)
            _finish_task(tenant, user_id, receiver_id)
        sender_id = _start(tenant, user_id, "Order", message_start=message_start)
        return tenant, user_id, sender_id, receiver_id

    def statuses(tenant):
        with tenant_session(tenant) as session:
            instances = list(session.scalars(select(ProcessInstanceModel)))
            assert {instance.collaboration_correlation_key for instance in instances} == {KEY}
            return {instance.id: instance.status for instance in instances}

    def deliver(tenant, user_id, sender_id, receiver_id):
        _finish_task(tenant, user_id, sender_id)
        with tenant_session(tenant) as session:
            assert workflow.run_due(session, tenant_id=tenant, now=datetime.now(UTC)) == 1
        after = statuses(tenant)
        assert after.pop(sender_id) == "complete"
        if receiver_id is None:
            assert list(after.values()) == ["complete"]
        else:
            assert after == {receiver_id: "complete"}

    tenant_a = setup("collaboration-a")
    tenant_b = setup("collaboration-b")
    before = []
    for tenant, _, sender_id, receiver_id in (tenant_a, tenant_b):
        expected = {sender_id: "user_input_required"}
        if receiver_id is not None:
            expected[receiver_id] = "waiting"
        assert statuses(tenant) == expected
        before.append(expected)

    deliver(*tenant_a)
    assert statuses(tenant_b[0]) == before[1]
    after_a = statuses(tenant_a[0])
    deliver(*tenant_b)
    assert statuses(tenant_a[0]) == after_a
