from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME


def _login_user(
    client, db_session, *, username: str, groups: list[str], tenant_id: str, v1_role: str = "user"
):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(
        db_session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=username,
    )
    ensure_membership(db_session, user, ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id))
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name=v1_role, user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user, token


def _seed_instance(
    db_session,
    *,
    tenant_id: str,
    initiator_id: int,
    process_model_identifier: str,
    start: int | None,
    status: str = "complete",
    bpmn_process_definition_id: int | None = None,
    last_milestone_bpmn_name: str | None = None,
    updated_at: int | None = None,
):
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    now = int(time.time())
    terminal = status in {"complete", "error", "terminated"}
    instance = ProcessInstanceModel(
        m8f_tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        process_model_display_name=process_model_identifier.split("/")[-1],
        process_initiator_id=initiator_id,
        bpmn_process_definition_id=bpmn_process_definition_id,
        status=status,
        started_at=datetime.fromtimestamp(start, UTC) if start is not None else None,
        ended_at=datetime.fromtimestamp(start + 60, UTC) if start is not None and terminal else None,
        created_at=datetime.fromtimestamp(now, UTC),
        updated_at=datetime.fromtimestamp(updated_at if updated_at is not None else now, UTC),
        last_milestone_bpmn_name=last_milestone_bpmn_name,
    )
    db_session.add(instance)
    db_session.flush()
    return instance


def _seed_definition_with_tasks(
    db_session,
    *,
    tenant_id: str,
    process_instance,
    bpmn_xml: str = "<definitions/>",
    task_states: dict[str, str] | None = None,
):
    """Seeds a BpmnProcessDefinition (source_bpmn_xml) + BpmnProcess +
    TaskDefinition/Task rows for the given instance, wires
    process_instance.bpmn_process_definition_id, and returns the
    definition. `task_states` maps bpmn_identifier -> TaskModel.state.
    """
    from m8flow_bpmn_core.models.bpmn_process import BpmnProcessModel
    from m8flow_bpmn_core.models.bpmn_process_definition import (
        SOURCE_BPMN_XML_PROPERTY_KEY,
        BpmnProcessDefinitionModel,
    )
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel

    definition = BpmnProcessDefinitionModel(
        m8f_tenant_id=tenant_id,
        single_process_hash=uuid.uuid4().hex,
        bpmn_identifier="Process_1",
        properties_json={SOURCE_BPMN_XML_PROPERTY_KEY: bpmn_xml},
    )
    db_session.add(definition)
    db_session.flush()

    process_instance.bpmn_process_definition_id = definition.id
    db_session.flush()

    bpmn_process = BpmnProcessModel(
        m8f_tenant_id=tenant_id,
        bpmn_process_definition_id=definition.id,
        properties_json={},
        json_data_hash=uuid.uuid4().hex,
    )
    db_session.add(bpmn_process)
    db_session.flush()

    for bpmn_identifier, state in (task_states or {}).items():
        task_definition = TaskDefinitionModel(
            m8f_tenant_id=tenant_id,
            bpmn_process_definition_id=definition.id,
            bpmn_identifier=bpmn_identifier,
            bpmn_name=None,
            typename="Task",
            properties_json={},
        )
        db_session.add(task_definition)
        db_session.flush()

        task = TaskModel(
            m8f_tenant_id=tenant_id,
            guid=str(uuid.uuid4()),
            bpmn_process_id=bpmn_process.id,
            process_instance_id=process_instance.id,
            task_definition_id=task_definition.id,
            state=state,
            properties_json={},
            json_data_hash=uuid.uuid4().hex,
            python_env_data_hash=uuid.uuid4().hex,
        )
        db_session.add(task)
    db_session.flush()
    return definition


def test_editor_lists_instances_with_pagination(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now - 60,
        status="complete",
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now - 30,
        status="running",
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-instances",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"] == {"count": 2, "total": 2, "pages": 1}
    assert [row["status"] for row in body["results"]] == ["running", "complete"]  # newest first
    assert body["results"][0]["started_by"] == "editor"


def test_status_and_search_filters(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor2", groups=["t1:editor"], tenant_id="t1"
    )
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now,
        status="complete",
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="onboarding/new-hire",
        start=now,
        status="error",
    )
    db_session.commit()

    by_status = client.get(
        "/v1.0/m8flow/process-instances?status=error",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert by_status.status_code == 200
    assert [r["process_model_identifier"] for r in by_status.get_json()["results"]] == ["onboarding/new-hire"]

    by_search = client.get(
        "/v1.0/m8flow/process-instances?search=invoice",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert by_search.status_code == 200
    assert [r["process_model_identifier"] for r in by_search.get_json()["results"]] == [
        "finance/invoice-approval"
    ]


def test_pagination_pages(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor3", groups=["t1:editor"], tenant_id="t1"
    )
    now = int(time.time())
    for i in range(3):
        _seed_instance(
            db_session,
            tenant_id="t1",
            initiator_id=user.id,
            process_model_identifier="finance/invoice-approval",
            start=now - i,
            status="complete",
        )
    db_session.commit()

    page1 = client.get(
        "/v1.0/m8flow/process-instances?per_page=2&page=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    body1 = page1.get_json()
    assert body1["pagination"] == {"count": 2, "total": 3, "pages": 2}

    page2 = client.get(
        "/v1.0/m8flow/process-instances?per_page=2&page=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    body2 = page2.get_json()
    assert body2["pagination"] == {"count": 1, "total": 3, "pages": 2}


def test_reviewer_gets_empty_page(client, db_session):
    """reviewer lacks the process-instance list grant (and editor
    fallback) in this test's unsynced-YAML fixture setup — [] not 403,
    same convention as list_process_models."""
    user, token = _login_user(
        client, db_session, username="reviewer", groups=["t1:reviewer"], tenant_id="t1"
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-instances",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"results": [], "pagination": {"count": 0, "total": 0, "pages": 0}}


def test_super_admin_lists_all_tenants_without_cookie(client, db_session):
    """No cookie + no tenantId == "All Tenants" for a super-admin: the merged
    cross-tenant list, each row tagged with its owning tenant. `?tenantId=`
    still narrows. Non-super-admins are unaffected (see the isolation tests
    below), because resolve_read_tenant_id delegates them to require_tenant_id.
    """
    user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now,
    )
    _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user.id,
        process_model_identifier="hr/onboarding",
        start=now,
    )
    db_session.commit()
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)

    merged = client.get(
        "/v1.0/m8flow/process-instances",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert merged.status_code == 200
    rows = merged.get_json()["results"]
    assert {row["tenant_id"] for row in rows} == {"t1", "t2"}

    scoped = client.get(
        "/v1.0/m8flow/process-instances?tenantId=t1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert scoped.status_code == 200
    assert {row["tenant_id"] for row in scoped.get_json()["results"]} == {"t1"}


def test_super_admin_opens_any_tenants_instance_detail_without_cookie(client, db_session):
    """Detail + every tab open cross-tenant under All Tenants. Instance ids are
    globally unique, so no tenant is needed to resolve one."""
    user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user.id,
        process_model_identifier="hr/onboarding",
        start=int(time.time()),
    )
    db_session.commit()
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)

    headers = {"Authorization": f"Bearer {token}"}
    detail = client.get(f"/v1.0/m8flow/process-instances/{instance.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.get_json()["tenant_id"] == "t2"

    for tab in ("events", "milestones", "completable-tasks", "pending-tasks", "completed-tasks"):
        response = client.get(
            f"/v1.0/m8flow/process-instances/{instance.id}/{tab}", headers=headers
        )
        assert response.status_code == 200, tab


def test_super_admin_lifecycle_write_still_requires_concrete_tenant(client, db_session):
    """Reads relax under All Tenants; writes must not. A lifecycle change has
    to land in exactly one tenant."""
    user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user.id,
        process_model_identifier="hr/onboarding",
        start=int(time.time()),
        status="running",
    )
    db_session.commit()
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)

    response = client.post(
        f"/v1.0/m8flow/process-instances/{instance.id}/terminate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_required"


def test_tenant_isolation_across_instances(client, db_session):
    """A t2-scoped instance never appears in t1's list."""
    user1, token1 = _login_user(
        client, db_session, username="editor-t1", groups=["t1:editor"], tenant_id="t1"
    )
    user2, _token2 = _login_user(
        client, db_session, username="editor-t2", groups=["t2:editor"], tenant_id="t2"
    )
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user1.id,
        process_model_identifier="finance/invoice-approval",
        start=now,
    )
    _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/other",
        start=now,
    )
    db_session.commit()

    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")
    response = client.get(
        "/v1.0/m8flow/process-instances",
        headers={"Authorization": f"Bearer {token1}"},
    )
    body = response.get_json()
    assert [r["process_model_identifier"] for r in body["results"]] == ["finance/invoice-approval"]


def test_editor_gets_instance_detail_with_bpmn_xml_and_task_states(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor4", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
        last_milestone_bpmn_name="Invoice Approval",
    )
    _seed_definition_with_tasks(
        db_session,
        tenant_id="t1",
        process_instance=instance,
        bpmn_xml="<definitions>seeded</definitions>",
        task_states={"StartEvent_1": "COMPLETED", "Activity_1": "WAITING"},
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["id"] == instance.id
    assert body["status"] == "waiting"
    assert body["started_by"] == "editor4"
    assert body["updated_at"] == instance.updated_at.isoformat()
    assert body["last_milestone_bpmn_name"] == "Invoice Approval"
    assert "revision" not in body
    assert "bpmn_version_control_identifier" not in body
    assert body["bpmn_xml"] == "<definitions>seeded</definitions>"
    tasks_by_id = {t["bpmn_identifier"]: t["state"] for t in body["tasks"]}
    assert tasks_by_id == {"StartEvent_1": "COMPLETED", "Activity_1": "WAITING"}


def test_instance_detail_without_definition_has_null_bpmn_xml_and_no_tasks(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor5", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["bpmn_xml"] is None
    assert body["tasks"] == []
    assert body["last_milestone_bpmn_name"] is None
    assert body["updated_at"] is not None


def test_missing_instance_is_404(client, db_session):
    _user, token = _login_user(
        client, db_session, username="editor6", groups=["t1:editor"], tenant_id="t1"
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-instances/999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_instance_from_another_tenant_is_404_not_leaked(client, db_session):
    """Tenant isolation on the detail route: an instance that exists, just
    not in the caller's tenant, must 404 like it doesn't exist at all."""
    user2, _token2 = _login_user(
        client, db_session, username="editor-other-tenant", groups=["t2:editor"], tenant_id="t2"
    )
    other_instance = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/other",
        start=int(time.time()),
    )
    db_session.commit()

    _user1, token1 = _login_user(
        client, db_session, username="editor-t1-detail", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{other_instance.id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 404


def _seed_other_user(db_session, *, tenant_id: str, username: str):
    """A second initiator (no login/token needed) so owner-filter/owners
    tests can span more than one started_by."""
    user = ensure_user(
        db_session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=username,
    )
    ensure_membership(
        db_session, user, ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    )
    db_session.flush()
    return user


def _seed_pending_task(
    db_session,
    *,
    tenant_id: str,
    process_instance_id: int,
    assignee_user_id: int,
    task_title: str | None = "Submit Expense Claim",
    task_name: str = "submit_claim",
    lane_name: str | None = "Submitter",
    completed: bool = False,
    completed_by_user_id: int | None = None,
    updated_at: int | None = None,
):
    from m8flow_bpmn_core.models.human_task import HumanTaskModel
    from m8flow_bpmn_core.models.human_task_user import HumanTaskUserModel

    now = int(time.time())
    task = HumanTaskModel(
        m8f_tenant_id=tenant_id,
        process_instance_id=process_instance_id,
        task_name=task_name,
        task_title=task_title,
        task_type="UserTask",
        task_status="COMPLETED" if completed else "READY",
        process_model_display_name="Invoice Approval",
        bpmn_process_identifier="Process_1",
        lane_name=lane_name,
        completed=completed,
        completed_by_user_id=completed_by_user_id,
        created_at=datetime.fromtimestamp(now, UTC),
        updated_at=datetime.fromtimestamp(updated_at if updated_at is not None else now, UTC),
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        HumanTaskUserModel(
            m8f_tenant_id=tenant_id,
            human_task_id=task.id,
            user_id=assignee_user_id,
        )
    )
    db_session.flush()
    return task


def test_started_by_filter(client, db_session):
    user, token = _login_user(
        client, db_session, username="alice", groups=["t1:editor"], tenant_id="t1"
    )
    bob = _seed_other_user(db_session, tenant_id="t1", username="bob")
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now,
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=bob.id,
        process_model_identifier="onboarding/new-hire",
        start=now,
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-instances?started_by=bob",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"]["total"] == 1
    assert [r["started_by"] for r in body["results"]] == ["bob"]


def test_sort_oldest_and_recent_start(client, db_session):
    user, token = _login_user(
        client, db_session, username="sorter", groups=["t1:editor"], tenant_id="t1"
    )
    now = int(time.time())
    # Insert out of id/time order so sort actually reorders rows.
    first = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/a",
        start=now - 100,
    )
    second = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/b",
        start=now - 10,
    )
    db_session.commit()

    newest = client.get(
        "/v1.0/m8flow/process-instances",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert [r["id"] for r in newest["results"]] == [second.id, first.id]

    oldest = client.get(
        "/v1.0/m8flow/process-instances?sort=oldest",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert [r["id"] for r in oldest["results"]] == [first.id, second.id]

    recent_start = client.get(
        "/v1.0/m8flow/process-instances?sort=recent_start",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert [r["id"] for r in recent_start["results"]] == [second.id, first.id]

    # Unknown sort falls back to newest, no error.
    fallback = client.get(
        "/v1.0/m8flow/process-instances?sort=bogus",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert fallback.status_code == 200
    assert [r["id"] for r in fallback.get_json()["results"]] == [second.id, first.id]


def test_owners_route_returns_distinct_sorted_usernames(client, db_session):
    user, token = _login_user(
        client, db_session, username="Zoe", groups=["t1:editor"], tenant_id="t1"
    )
    amir = _seed_other_user(db_session, tenant_id="t1", username="amir")
    now = int(time.time())
    # Zoe initiates two, amir one -> owners is deduped + case-insensitively sorted.
    for i in range(2):
        _seed_instance(
            db_session,
            tenant_id="t1",
            initiator_id=user.id,
            process_model_identifier="finance/invoice-approval",
            start=now - i,
        )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=amir.id,
        process_model_identifier="onboarding/new-hire",
        start=now,
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-instances/owners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "owners": ["amir", "Zoe"],
        "owner_options": [
            {"id": amir.id, "username": "amir"},
            {"id": user.id, "username": "Zoe"},
        ],
    }


def test_owners_route_is_tenant_scoped(client, db_session):
    user1, token1 = _login_user(
        client, db_session, username="owner-t1", groups=["t1:editor"], tenant_id="t1"
    )
    user2 = _seed_other_user(db_session, tenant_id="t2", username="owner-t2")
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user1.id,
        process_model_identifier="finance/a",
        start=now,
    )
    _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/b",
        start=now,
    )
    db_session.commit()

    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")
    response = client.get(
        "/v1.0/m8flow/process-instances/owners",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "owners": ["owner-t1"],
        "owner_options": [{"id": user1.id, "username": "owner-t1"}],
    }


def test_owners_route_empty_for_denied_caller(client, db_session):
    _user, token = _login_user(
        client, db_session, username="reviewer-owners", groups=["t1:reviewer"], tenant_id="t1"
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-instances/owners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"owners": [], "owner_options": []}


def test_editor_lists_instance_events_with_task_definition_columns(client, db_session):
    """Events tab: Task → TaskDefinition labels, not HumanTask.task_title.
    Null actor becomes ``system``. Instance-level events have empty BPMN cells.
    """
    from m8flow_bpmn_core.models.human_task import HumanTaskModel
    from m8flow_bpmn_core.models.process_instance_event import ProcessInstanceEventModel
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel

    user, token = _login_user(
        client, db_session, username="editor-events", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    _seed_definition_with_tasks(
        db_session,
        tenant_id="t1",
        process_instance=instance,
        bpmn_xml="<definitions/>",
        task_states={"Event_0jqbb0y": "COMPLETED"},
    )
    task = db_session.query(TaskModel).filter_by(process_instance_id=instance.id).one()
    task_def = db_session.get(TaskDefinitionModel, task.task_definition_id)
    task_def.typename = "StartEvent"
    task_def.bpmn_name = None

    db_session.add(
        HumanTaskModel(
            m8f_tenant_id="t1",
            process_instance_id=instance.id,
            task_guid=task.guid,
            task_name="submit_claim",
            task_title="Submit Expense Claim",
            task_type="UserTask",
            task_status="COMPLETED",
            process_model_display_name="Invoice Approval",
            bpmn_process_identifier="should-not-appear",
            completed=True,
            created_at=datetime.fromtimestamp(1, UTC),
        )
    )
    db_session.add(
        ProcessInstanceEventModel(
            m8f_tenant_id="t1",
            process_instance_id=instance.id,
            event_type="process_instance_created",
            occurred_at=datetime.fromtimestamp(1756000100.0, UTC),
        )
    )
    db_session.add(
        ProcessInstanceEventModel(
            m8f_tenant_id="t1",
            process_instance_id=instance.id,
            event_type="task_completed",
            occurred_at=datetime.fromtimestamp(1756000200.5, UTC),
            task_guid=task.guid,
        )
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    rows = response.get_json()["results"]
    assert [r["event_type"] for r in rows] == [
        "process_instance_created",
        "task_completed",
    ]
    created, completed = rows
    assert created["user"] == "system"
    assert created["bpmn_process"] is None
    assert created["task_name"] is None
    assert created["task_identifier"] is None
    assert created["task_type"] is None
    assert completed["user"] == "system"
    assert completed["bpmn_process"] == "Process_1"
    assert completed["task_name"] is None
    assert completed["task_identifier"] == "Event_0jqbb0y"
    assert completed["task_type"] == "StartEvent"
    assert completed["task_name"] != "Submit Expense Claim"
    assert completed["task_guid"] == task.guid
    assert "task_title" not in completed


def test_instance_events_include_every_bpmn_task_type(client, db_session):
    """Core logs only human-task completion and service-task failure, so
    start/script tasks come from task rows (Spiff last_state_change). Spiff
    bookkeeping (BpmnStartTask, BoundaryEventJoin) and unreached (FUTURE)
    tasks stay hidden; the
    real task_failed event is not duplicated and carries the recorded error."""
    token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-events-all")
    _add_error(db_session, instance=instance, task_guid=tasks["Service_1"].guid, message="proxy said 502")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/events",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.get_json()
    rows = body["results"]
    assert [(r["task_identifier"], r["task_type"], r["event_type"]) for r in rows] == [
        ("StartEvent_1", "StartEvent", "task_completed"),
        ("Script_1", "ScriptTask", "task_completed"),
        ("Service_1", "ServiceTask", "task_failed"),
    ]
    start, script, service = rows
    assert start["id"] is None and start["user"] == "system"
    assert start["occurred_at"] == datetime.fromtimestamp(100.25, UTC).isoformat()
    assert script["task_guid"] == tasks["Script_1"].guid
    assert isinstance(service["id"], int)
    assert service["error_message"] == "proxy said 502"
    assert script["error_message"] is None
    assert body["pagination"] == {"count": 3, "total": 3, "pages": 1}
    assert body["filter_options"] == {
        "event_types": ["task_completed", "task_failed"],
        "task_types": ["ScriptTask", "ServiceTask", "StartEvent"],
    }


def test_instance_events_filter_and_paginate(client, db_session):
    token, instance, _tasks = _seed_mixed_task_events(client, db_session, username="editor-events-page")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/events?event_type=task_completed&per_page=1&page=2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert [r["task_identifier"] for r in body["results"]] == ["Script_1"]
    assert body["pagination"] == {"count": 1, "total": 2, "pages": 2}
    # Options describe the unfiltered log so the dropdown never empties itself.
    assert body["filter_options"]["event_types"] == ["task_completed", "task_failed"]

    by_type = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/events?task_type=ServiceTask",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert [r["task_identifier"] for r in by_type["results"]] == ["Service_1"]


def test_instance_events_missing_instance_is_404(client, db_session):
    _user, token = _login_user(
        client, db_session, username="editor-events-404", groups=["t1:editor"], tenant_id="t1"
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-instances/999999/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_instance_events_from_another_tenant_is_404(client, db_session):
    user2, _token2 = _login_user(
        client, db_session, username="editor-events-t2", groups=["t2:editor"], tenant_id="t2"
    )
    other = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/other",
        start=int(time.time()),
    )
    db_session.commit()

    _user1, token1 = _login_user(
        client, db_session, username="editor-events-t1", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{other.id}/events",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 404


def test_editor_lists_one_current_milestone_not_a_history(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-milestones", groups=["t1:editor"], tenant_id="t1"
    )
    start = 1_783_380_927
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=start,
        status="waiting",
        last_milestone_bpmn_name="Invoice Approval",
    )
    _seed_definition_with_tasks(
        db_session,
        tenant_id="t1",
        process_instance=instance,
        bpmn_xml="<definitions/>",
        task_states={},
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/milestones",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    rows = response.get_json()["results"]
    assert len(rows) == 1
    assert rows[0] == {
        "milestone": "Invoice Approval",
        "bpmn_process": "Process_1",
        "started_at": datetime.fromtimestamp(start, UTC).isoformat(),
    }


def test_milestones_empty_when_last_milestone_unset(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-milestones-empty", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/milestones",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json()["results"] == []


def test_instance_milestones_from_another_tenant_is_404(client, db_session):
    user2, _token2 = _login_user(
        client, db_session, username="editor-milestones-t2", groups=["t2:editor"], tenant_id="t2"
    )
    other = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/other",
        start=int(time.time()),
        last_milestone_bpmn_name="Other",
    )
    db_session.commit()

    _user1, token1 = _login_user(
        client, db_session, username="editor-milestones-t1", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{other.id}/milestones",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 404


def test_editor_suspends_and_resumes_instance(client, db_session):
    """Editor uses the default V1 user role — host YAML / allow_uri must
    be enough; do not require the core V1 admin role."""
    user, token = _login_user(
        client, db_session, username="editor-lifecycle", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    db_session.commit()

    suspended = client.post(
        f"/v1.0/m8flow/process-instances/{instance.id}/suspend",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert suspended.status_code == 200
    assert suspended.get_json() == {"id": instance.id, "status": "suspended"}

    resumed = client.post(
        f"/v1.0/m8flow/process-instances/{instance.id}/resume",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resumed.status_code == 200
    assert resumed.get_json()["status"] == "running"


def test_editor_terminates_instance(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-terminate", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    db_session.commit()

    response = client.post(
        f"/v1.0/m8flow/process-instances/{instance.id}/terminate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"id": instance.id, "status": "terminated"}


def test_terminate_complete_instance_is_409(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-terminate-complete", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="complete",
    )
    db_session.commit()

    response = client.post(
        f"/v1.0/m8flow/process-instances/{instance.id}/terminate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "invalid_state"


def test_viewer_cannot_suspend_instance(client, db_session):
    user, token = _login_user(
        client, db_session, username="viewer-lifecycle", groups=["t1:viewer"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    db_session.commit()

    response = client.post(
        f"/v1.0/m8flow/process-instances/{instance.id}/suspend",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.get_json()["error_code"] == "permission_denied"


def test_lifecycle_other_tenant_is_404(client, db_session):
    user2, _token2 = _login_user(
        client, db_session, username="editor-lifecycle-t2", groups=["t2:editor"], tenant_id="t2"
    )
    other = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/other",
        start=int(time.time()),
        status="waiting",
    )
    db_session.commit()

    _user1, token1 = _login_user(
        client, db_session, username="editor-lifecycle-t1", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")

    response = client.post(
        f"/v1.0/m8flow/process-instances/{other.id}/terminate",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 404


def test_editor_lists_only_own_incomplete_candidate_tasks(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-completable", groups=["t1:editor"], tenant_id="t1"
    )
    other = _seed_other_user(db_session, tenant_id="t1", username="other-candidate")
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    mine = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=user.id,
        task_title="Submit Expense Claim",
        task_name="submit_claim",
        lane_name="Submitter",
    )
    _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=other.id,
        task_title="Manager Review",
        task_name="manager_review",
        lane_name="Manager",
    )
    _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=user.id,
        task_title="Already done",
        task_name="done_step",
        completed=True,
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/completable-tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    rows = response.get_json()["results"]
    assert rows[0].pop("waiting_for")["type"] == "user"
    assert rows == [
        {
            "id": mine.id,
            "task_title": "Submit Expense Claim",
            "task_name": "submit_claim",
            "lane_name": "Submitter",
        }
    ]
    assert "name" not in rows[0]


def test_pending_tasks_show_waiting_for_and_can_complete(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-pending", groups=["t1:editor"], tenant_id="t1"
    )
    other = _seed_other_user(db_session, tenant_id="t1", username="the-approver")
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    theirs = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=other.id,
        task_title="Manager Review",
        task_name="manager_review",
        lane_name="Manager",
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/pending-tasks", headers=headers
    )
    assert response.status_code == 200
    rows = response.get_json()["results"]
    assert [row["id"] for row in rows] == [theirs.id]
    assert rows[0]["can_complete"] is False
    assert rows[0]["waiting_for"]["type"] == "user"
    assert rows[0]["waiting_for"]["label"] == "the-approver"
    # Still not offered under Tasks I can complete.
    completable = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/completable-tasks", headers=headers
    )
    assert completable.get_json()["results"] == []


def test_pending_tasks_from_another_tenant_is_404(client, db_session):
    user2, _token2 = _login_user(
        client, db_session, username="editor-pending-t2", groups=["t2:editor"], tenant_id="t2"
    )
    other = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/other",
        start=int(time.time()),
        status="waiting",
    )
    db_session.commit()
    _user1, token1 = _login_user(
        client, db_session, username="editor-pending-t1", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")
    response = client.get(
        f"/v1.0/m8flow/process-instances/{other.id}/pending-tasks",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 404


def test_completable_tasks_empty_when_instance_is_suspended(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-suspended-completable", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="suspended",
    )
    _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=user.id,
        task_title="Submit Expense Claim",
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/completable-tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json()["results"] == []


def test_completable_tasks_empty_when_caller_is_not_a_candidate(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-not-candidate", groups=["t1:editor"], tenant_id="t1"
    )
    other = _seed_other_user(db_session, tenant_id="t1", username="the-candidate")
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=other.id,
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/completable-tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json()["results"] == []


def test_completable_tasks_from_another_tenant_is_404(client, db_session):
    user2, _token2 = _login_user(
        client, db_session, username="editor-completable-t2", groups=["t2:editor"], tenant_id="t2"
    )
    other = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/other",
        start=int(time.time()),
        status="waiting",
    )
    db_session.commit()

    _user1, token1 = _login_user(
        client, db_session, username="editor-completable-t1", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{other.id}/completable-tasks",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 404


def test_editor_lists_completed_by_me_and_all_completed(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-completed", groups=["t1:editor"], tenant_id="t1"
    )
    other = _seed_other_user(db_session, tenant_id="t1", username="other-completer")
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    mine = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=user.id,
        task_title="Submit Expense Claim",
        task_name="submit_claim",
        completed=True,
        completed_by_user_id=user.id,
        updated_at=1_100,
    )
    theirs = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=other.id,
        task_title=None,
        task_name="manager_review",
        completed=True,
        completed_by_user_id=other.id,
        updated_at=2_100,
    )
    _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=user.id,
        task_title="Still open",
        task_name="still_open",
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/completed-tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    mine_by = user.display_name or user.username
    other_by = other.display_name or other.username
    assert payload["completed_by_me"] == [
        {
            "id": mine.id,
            "task_title": "Submit Expense Claim",
            "task_name": "submit_claim",
            "completed_by": mine_by,
            "updated_at": "1970-01-01T00:18:20+00:00",
        }
    ]
    assert payload["all_completed"] == [
        {
            "id": mine.id,
            "task_title": "Submit Expense Claim",
            "task_name": "submit_claim",
            "completed_by": mine_by,
            "updated_at": "1970-01-01T00:18:20+00:00",
        },
        {
            "id": theirs.id,
            "task_title": None,
            "task_name": "manager_review",
            "completed_by": other_by,
            "updated_at": "1970-01-01T00:35:00+00:00",
        },
    ]
    assert "name" not in payload["all_completed"][0]


def test_completed_tasks_from_another_tenant_is_404(client, db_session):
    user2, _token2 = _login_user(
        client, db_session, username="editor-completed-t2", groups=["t2:editor"], tenant_id="t2"
    )
    other = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/other",
        start=int(time.time()),
        status="waiting",
    )
    db_session.commit()

    _user1, token1 = _login_user(
        client, db_session, username="editor-completed-t1", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{other.id}/completed-tasks",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 404


def test_editor_deletes_finished_instance(client, db_session):
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    user, token = _login_user(
        client, db_session, username="editor-delete", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="complete",
    )
    db_session.commit()
    instance_id = instance.id

    response = client.delete(
        f"/v1.0/m8flow/process-instances/{instance_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"id": instance_id, "deleted": True}
    db_session.expire_all()
    assert db_session.get(ProcessInstanceModel, instance_id) is None

    again = client.delete(
        f"/v1.0/m8flow/process-instances/{instance_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert again.status_code == 404


def test_delete_active_instance_is_409(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor-delete-active", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="waiting",
    )
    db_session.commit()

    response = client.delete(
        f"/v1.0/m8flow/process-instances/{instance.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "process_instance_not_finished"


def test_viewer_cannot_delete_instance(client, db_session):
    user, token = _login_user(
        client, db_session, username="viewer-delete", groups=["t1:viewer"], tenant_id="t1"
    )
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
        status="complete",
    )
    db_session.commit()

    response = client.delete(
        f"/v1.0/m8flow/process-instances/{instance.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_delete_other_tenant_instance_is_404(client, db_session):
    user2, _token2 = _login_user(
        client, db_session, username="editor-delete-t2", groups=["t2:editor"], tenant_id="t2"
    )
    other = _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=user2.id,
        process_model_identifier="finance/other",
        start=int(time.time()),
        status="complete",
    )
    db_session.commit()
    _user1, token1 = _login_user(
        client, db_session, username="editor-delete-t1", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")

    response = client.delete(
        f"/v1.0/m8flow/process-instances/{other.id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 404


def _seed_mixed_task_events(client, db_session, *, username: str, status: str = "error"):
    """An instance whose task rows cover the Events-tab cases: real BPMN tasks
    (start / script / service), Spiff bookkeeping tasks (BpmnStartTask, a
    boundary-event join), and a not-yet-reached task. Service_1 also has
    core's real ``task_failed`` event. Returns (token, instance,
    tasks_by_bpmn_identifier)."""
    from m8flow_bpmn_core.models.process_instance_event import ProcessInstanceEventModel
    from m8flow_bpmn_core.models.task import TaskModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel

    user, token = _login_user(client, db_session, username=username, groups=["t1:editor"], tenant_id="t1")
    instance = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/all-events",
        start=int(time.time()),
        status=status,
    )
    _seed_definition_with_tasks(
        db_session,
        tenant_id="t1",
        process_instance=instance,
        task_states={
            "Root_Start": "COMPLETED",
            "StartEvent_1": "COMPLETED",
            "Script_1": "COMPLETED",
            "Script_1.BoundaryEventJoin": "COMPLETED",
            "Service_1": "ERROR",
            "Later_1": "FUTURE",
        },
    )
    typenames = {
        "Root_Start": "BpmnStartTask",
        "StartEvent_1": "StartEvent",
        "Script_1": "ScriptTask",
        "Script_1.BoundaryEventJoin": "BoundaryEventJoin",
        "Service_1": "ServiceTask",
        "Later_1": "UserTask",
    }
    stamps = {
        "Root_Start": 100.0,
        "StartEvent_1": 100.25,
        "Script_1": 101.5,
        "Script_1.BoundaryEventJoin": 101.75,
        "Service_1": 102.75,
        "Later_1": 99.0,
    }
    tasks = {}
    for task, task_def in (
        db_session.query(TaskModel, TaskDefinitionModel)
        .join(TaskDefinitionModel, TaskDefinitionModel.id == TaskModel.task_definition_id)
        .filter(TaskModel.process_instance_id == instance.id)
    ):
        task_def.typename = typenames[task_def.bpmn_identifier]
        task.properties_json = {"last_state_change": stamps[task_def.bpmn_identifier]}
        tasks[task_def.bpmn_identifier] = task
    db_session.add(
        ProcessInstanceEventModel(
            m8f_tenant_id="t1",
            process_instance_id=instance.id,
            event_type="task_failed",
            occurred_at=datetime.fromtimestamp(102.0, UTC),
            task_guid=tasks["Service_1"].guid,
        )
    )
    db_session.commit()
    return token, instance, tasks


def _add_error(db_session, *, instance, task_guid, message):
    from m8flow_backend.models.process_instance_error import ProcessInstanceErrorModel

    db_session.add(
        ProcessInstanceErrorModel(
            m8f_tenant_id="t1",
            process_instance_id=instance.id,
            task_guid=task_guid,
            message=message,
            created_at_in_seconds=int(time.time()),
        )
    )
    db_session.commit()


def test_instance_detail_tasks_carry_guid_type_and_state_change(client, db_session):
    token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-detail-tasks")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    by_id = {t["bpmn_identifier"]: t for t in response.get_json()["tasks"]}
    assert by_id["Script_1"] == {
        "guid": tasks["Script_1"].guid,
        "bpmn_identifier": "Script_1",
        "bpmn_name": None,
        "typename": "ScriptTask",
        "state": "COMPLETED",
        "last_state_change": 101.5,
    }


def test_instance_detail_to_task_guid_keeps_only_tasks_finished_by_then(client, db_session):
    token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-time-travel")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}?to_task_guid={tasks['Script_1'].guid}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert {t["bpmn_identifier"] for t in response.get_json()["tasks"]} == {
        "Root_Start",
        "StartEvent_1",
        "Script_1",
    }


def test_instance_detail_to_task_guid_rejects_unfinished_or_foreign_task(client, db_session):
    token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-time-travel-bad")
    headers = {"Authorization": f"Bearer {token}"}

    future = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}?to_task_guid={tasks['Later_1'].guid}", headers=headers
    )
    unknown = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}?to_task_guid=not-a-task", headers=headers
    )

    assert future.status_code == 400
    assert unknown.status_code == 404


def test_instance_detail_error_message_only_for_errored_instance(client, db_session):
    token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-error-banner")
    _add_error(db_session, instance=instance, task_guid=tasks["Service_1"].guid, message="proxy said 502")
    headers = {"Authorization": f"Bearer {token}"}

    errored = client.get(f"/v1.0/m8flow/process-instances/{instance.id}", headers=headers).get_json()
    assert errored["error_message"] == "proxy said 502"

    instance.status = "running"
    db_session.commit()
    running = client.get(f"/v1.0/m8flow/process-instances/{instance.id}", headers=headers).get_json()
    assert running["error_message"] is None


def test_editor_reads_one_task_with_its_data(client, db_session):
    from m8flow_bpmn_core.models.json_data import JsonDataModel

    token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-task-data")
    script = tasks["Script_1"]
    script.json_data_hash = JsonDataModel.create_or_update_from_payload(db_session, "t1", {"invoice_total": 1250})
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/tasks/{script.guid}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "guid": script.guid,
        "bpmn_identifier": "Script_1",
        "bpmn_name": None,
        "typename": "ScriptTask",
        "state": "COMPLETED",
        "last_state_change": 101.5,
        "data": {"invoice_total": 1250},
    }


def test_task_without_own_data_falls_back_to_process_variables(client, db_session):
    """Core stores user-task submissions as process variables, not on the task,
    so a task's own json_data is usually {} -- show the process variables then
    (same fallback as the Task Review form), minus core's internal state key."""
    from m8flow_bpmn_core.models.bpmn_process import BpmnProcessModel
    from m8flow_bpmn_core.models.json_data import JsonDataModel

    token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-task-proc-data")
    script = tasks["Script_1"]
    bpmn_process = db_session.get(BpmnProcessModel, script.bpmn_process_id)
    bpmn_process.json_data_hash = JsonDataModel.create_or_update_from_payload(
        db_session, "t1", {"first_name": "Asha", "__m8f_workflow_state_json": "{}"}
    )
    instance.bpmn_process_id = bpmn_process.id
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/tasks/{script.guid}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {"first_name": "Asha"}


def test_task_of_another_instance_is_404(client, db_session):
    token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-task-other")
    _token2, other, other_tasks = _seed_mixed_task_events(client, db_session, username="editor-task-other-2")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/tasks/{other_tasks['Script_1'].guid}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_task_from_another_tenant_is_404(client, db_session):
    _token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-task-t1")
    _user, token_t2 = _login_user(client, db_session, username="editor-task-t2", groups=["t2:editor"], tenant_id="t2")

    response = client.get(
        f"/v1.0/m8flow/process-instances/{instance.id}/tasks/{tasks['Script_1'].guid}",
        headers={"Authorization": f"Bearer {token_t2}"},
    )

    assert response.status_code == 404


def test_task_data_needs_the_read_task_data_grant(client, db_session):
    """``read-task-data`` (/task-data/*) gates the task modal's data: a
    submitter reads the instance but not its tasks' data; editor keeps it."""
    from m8flow_backend import identity

    editor_token, instance, tasks = _seed_mixed_task_events(client, db_session, username="editor-task-grant")
    _user, submitter_token = _login_user(
        client, db_session, username="submitter-task-grant", groups=["t1:submitter"], tenant_id="t1"
    )
    identity.import_yaml(db_session, tenant_id="t1")
    db_session.commit()
    task_url = f"/v1.0/m8flow/process-instances/{instance.id}/tasks/{tasks['Script_1'].guid}"

    def get(url, token):
        return client.get(url, headers={"Authorization": f"Bearer {token}"})

    assert get(f"/v1.0/m8flow/process-instances/{instance.id}", submitter_token).status_code == 200
    assert get(task_url, submitter_token).status_code == 404
    assert get(task_url, editor_token).status_code == 200
