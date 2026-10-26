"""BPMN lane assignment: core's deterministic lane ids against host lane groups."""

from __future__ import annotations

import pytest

from tests.integration.support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

MODEL = "requests/submit"
LANE = "Submitters"


def _titles(tenant_id: str, user_id: int) -> list[str]:
    from m8flow_backend import workflow

    with tenant_session(tenant_id) as session:
        return [t.task_title for t in workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=user_id)]


def test_lane_task_reaches_lane_members_only_and_a_late_joiner_after_reconcile():
    from m8flow_bpmn_core.models.work_item import WorkItemModel
    from m8flow_bpmn_core.models.work_item_user import WorkItemUserModel

    from m8flow_backend import identity, workflow

    tenant_id = new_tenant_id("lane")
    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        member = provision_member(session, tenant_id=tenant_id, role="submitter", name="member", lanes=(LANE,))
        outsider = provision_member(session, tenant_id=tenant_id, role="submitter", name="outsider")
        save_model(session, tenant_id=tenant_id, user_id=editor.id, path=MODEL, fixture="submitters_lane.bpmn")
    with tenant_session(tenant_id) as session:
        instance = workflow.start(session, tenant_id=tenant_id, user_id=editor.id, process_model_identifier=MODEL)

    assert _titles(tenant_id, member.id) == ["Submit Request"]
    assert _titles(tenant_id, outsider.id) == []
    assert _titles(tenant_id, editor.id) == []  # starting does not put the starter in the lane

    # The outsider joins the lane after the task materialized.
    with tenant_session(tenant_id) as session:
        identity.sync_lane_groups(
            session, user=session.merge(outsider), tenant_id=tenant_id, lane_group_identifiers=[LANE]
        )
    with tenant_session(tenant_id) as session:
        first = workflow.reconcile_pending_tasks_for_user(session, tenant_id=tenant_id, user_id=outsider.id)
    with tenant_session(tenant_id) as session:
        second = workflow.reconcile_pending_tasks_for_user(session, tenant_id=tenant_id, user_id=outsider.id)
    assert [item.process_instance_id for item in first] == [instance.id]
    assert second == []
    assert _titles(tenant_id, outsider.id) == ["Submit Request"]

    with tenant_session(tenant_id) as session:
        work_item = session.query(WorkItemModel).filter_by(process_instance_id=instance.id).one()
        assignees = {
            (row.user_id, row.added_by)
            for row in session.query(WorkItemUserModel).filter_by(work_item_id=work_item.id)
        }
        assert work_item.lane_assignment_id == workflow.api.resolve_lane_assignment_id(LANE, tenant_id)
        assert work_item.actual_owner_id is None
    assert (outsider.id, "lane_assignment") in assignees
    assert member.id in {user_id for user_id, _ in assignees}


def test_same_lane_name_in_another_tenant_does_not_receive_the_task():
    from m8flow_backend import workflow

    tenant_a = new_tenant_id("lane-a")
    tenant_b = new_tenant_id("lane-b")
    with tenant_session(tenant_b) as session:
        other = provision_member(session, tenant_id=tenant_b, role="submitter", lanes=(LANE,))
    with tenant_session(tenant_a) as session:
        editor = provision_member(session, tenant_id=tenant_a, role="editor")
        save_model(session, tenant_id=tenant_a, user_id=editor.id, path=MODEL, fixture="submitters_lane.bpmn")
    with tenant_session(tenant_a) as session:
        workflow.start(session, tenant_id=tenant_a, user_id=editor.id, process_model_identifier=MODEL)

    assert workflow.api.resolve_lane_assignment_id(LANE, tenant_a) != workflow.api.resolve_lane_assignment_id(
        LANE, tenant_b
    )
    assert _titles(tenant_b, other.id) == []
    with tenant_session(tenant_b) as session:
        assert workflow.reconcile_pending_tasks_for_user(session, tenant_id=tenant_b, user_id=other.id) == []
