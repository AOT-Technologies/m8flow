"""Tenant isolation of core data under PostgreSQL row-level security.

The host connects as a role without BYPASSRLS, so every core query runs with
``app.current_tenant`` set from the tenant context, as in production.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from tests.integration.support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

MODEL = "invoices/approval"


def _tenant_with_running_instance(label: str):
    from m8flow_backend import workflow

    tenant_id = new_tenant_id(label)
    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(session, tenant_id=tenant_id, user_id=editor.id, path=MODEL, fixture="invoice_approval_poc.bpmn")
    with tenant_session(tenant_id) as session:
        instance = workflow.start(session, tenant_id=tenant_id, user_id=editor.id, process_model_identifier=MODEL)
    with tenant_session(tenant_id) as session:
        (task,) = workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=editor.id)
    return tenant_id, editor.id, instance.id, task.id


def test_rls_hides_other_tenants_core_rows_from_the_runtime_role(admin_engine):
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.work_item import WorkItemModel

    tenant_a, _, instance_a, task_a = _tenant_with_running_instance("rls-a")
    tenant_b, _, instance_b, task_b = _tenant_with_running_instance("rls-b")

    # Unfiltered ORM reads: only RLS stands between the tenants here.
    with tenant_session(tenant_a) as session:
        visible_instances = set(session.scalars(sa.select(ProcessInstanceModel.id)))
        visible_tasks = set(session.scalars(sa.select(WorkItemModel.id)))
        assert session.get(ProcessInstanceModel, instance_b) is None
    assert instance_a in visible_instances and instance_b not in visible_instances
    assert task_a in visible_tasks and task_b not in visible_tasks

    # No tenant bound: RLS returns nothing rather than everything.
    with tenant_session(None) as session:
        assert session.scalars(sa.select(ProcessInstanceModel.id)).all() == []

    # The owner connection still sees both, so the rows really exist.
    with admin_engine.connect() as conn:
        tenants = set(
            conn.execute(
                sa.text("SELECT m8f_tenant_id FROM process_instance WHERE id IN (:a, :b)"),
                {"a": instance_a, "b": instance_b},
            ).scalars()
        )
    assert tenants == {tenant_a, tenant_b}


def test_host_listings_are_scoped_to_the_active_tenant():
    from m8flow_backend import workflow

    tenant_a, editor_a, instance_a, task_a = _tenant_with_running_instance("list-a")
    tenant_b, _editor_b, instance_b, _task_b = _tenant_with_running_instance("list-b")

    with tenant_session(tenant_a) as session:
        instances = workflow.list_instances(session, tenant_id=tenant_a)
        pending = workflow.list_pending_tasks(session, tenant_id=tenant_a, user_id=editor_a)
    assert [i.id for i in instances] == [instance_a]
    assert [t.id for t in pending] == [task_a]
    assert instance_b not in {i.id for i in instances}


def test_cannot_claim_another_tenants_work_item():
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_a, editor_a, _instance_a, _task_a = _tenant_with_running_instance("claim-a")
    tenant_b, _editor_b, _instance_b, task_b = _tenant_with_running_instance("claim-b")

    # Tenant A's editor names tenant B's work item while acting in tenant A:
    # hidden, so its existence does not leak.
    with pytest.raises(ApiError) as denied:
        with tenant_session(tenant_a) as session:
            workflow.claim(session, tenant_id=tenant_a, work_item_id=task_b, user_id=editor_a)
    assert (denied.value.status_code, denied.value.error_code) == (404, "not_found")

    # Naming tenant B outright, without being a member there: forbidden.
    with pytest.raises(ApiError) as cross:
        with tenant_session(tenant_b) as session:
            workflow.claim(session, tenant_id=tenant_b, work_item_id=task_b, user_id=editor_a)
    assert (cross.value.status_code, cross.value.error_code) == (403, "permission_denied")

    with tenant_session(tenant_b) as session:
        assert session.get(WorkItemModel, task_b).actual_owner_id is None
