from __future__ import annotations

import time

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME


def _login_user(client, db_session, *, username: str, groups: list[str], tenant_id: str):
    """Mirrors test_onboarding_and_tasks.py's helper of the same name."""
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(
        db_session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=username,
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user, token


def _seed_instance(db_session, *, tenant_id: str, initiator_id: int, status: str, start=None, end=None):
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    now = int(time.time())
    instance = ProcessInstanceModel(
        m8f_tenant_id=tenant_id,
        process_model_identifier="test/model",
        process_model_display_name="Test Model",
        process_initiator_id=initiator_id,
        status=status,
        start_in_seconds=start,
        end_in_seconds=end,
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
    )
    db_session.add(instance)
    db_session.flush()
    return instance


def _seed_pending_task(
    db_session,
    *,
    tenant_id: str,
    process_instance_id: int,
    assignee_user_id: int,
    task_title: str = "Approve request",
    task_name: str = "Approve",
    lane_name: str | None = "reviewers",
    created_at: int | None = None,
):
    from m8flow_bpmn_core.models.human_task import HumanTaskModel
    from m8flow_bpmn_core.models.human_task_user import HumanTaskUserModel

    now = created_at if created_at is not None else int(time.time())
    task = HumanTaskModel(
        m8f_tenant_id=tenant_id,
        process_instance_id=process_instance_id,
        task_name=task_name,
        task_title=task_title,
        task_type="UserTask",
        task_status="READY",
        process_model_display_name="Test Model",
        bpmn_process_identifier="test_process",
        lane_name=lane_name,
        completed=False,
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
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


def test_editor_sees_instance_and_task_stats_but_not_total_tenants(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="running")
    db_session.commit()

    response = client.get("/v1.0/m8flow/home-stats", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["active_process_instances"] == 1
    assert body["tasks_waiting_on_me"] == 0
    assert body["errors_needing_review"] == 0
    assert body["completed_today"] == 0
    # No super-admin grant -- total_tenants must stay null, not e.g. 0 or 1.
    assert body["total_tenants"] is None


def test_reviewer_gets_task_stats_but_null_instance_stats(client, db_session):
    """The central ticket-03 decision: reviewer has read-task-list but is
    deliberately excluded from read-process-instance-list (m8flow.yml) --
    the response must reflect that per-field, not 403 the whole request
    and not silently grant reviewer instance visibility either.
    """
    user, token = _login_user(
        client, db_session, username="reviewer", groups=["t1:reviewer"], tenant_id="t1"
    )
    _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="running")
    db_session.commit()

    response = client.get("/v1.0/m8flow/home-stats", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["tasks_waiting_on_me"] == 0
    assert body["active_process_instances"] is None
    assert body["errors_needing_review"] is None
    assert body["completed_today"] is None
    assert body["avg_completion_minutes"] is None
    assert body["total_tenants"] is None


def test_super_admin_sees_total_tenants(client, db_session):
    user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    response = client.get("/v1.0/m8flow/home-stats", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.get_json()
    assert isinstance(body["total_tenants"], int)
    assert body["total_tenants"] >= 1


def test_super_admin_home_works_without_selected_tenant_cookie(client, db_session):
    """Platform admins land with no m8flow_selected_tenant (All Tenants)."""
    user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)
    headers = {"Authorization": f"Bearer {token}"}

    stats = client.get("/v1.0/m8flow/home-stats", headers=headers)
    assert stats.status_code == 200
    assert isinstance(stats.get_json()["total_tenants"], int)

    recent = client.get("/v1.0/m8flow/home-recent-instances", headers=headers)
    assert recent.status_code == 200
    assert isinstance(recent.get_json(), list)

    tasks = client.get("/v1.0/m8flow/home-my-tasks", headers=headers)
    assert tasks.status_code == 200
    assert isinstance(tasks.get_json(), list)


def test_aggregate_counts_reflect_seeded_instances(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    now = int(time.time())
    midnight_today = now - (now % 86400)
    # 1 active, 1 error, 1 completed today (10 minutes = 600s), 1 completed
    # long ago (outside "today", excluded from completed_today but still
    # counted in the overall avg_completion_minutes).
    _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="running")
    _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="error")
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        status="complete",
        start=midnight_today + 100,
        end=midnight_today + 100 + 600,
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        status="complete",
        start=midnight_today - 10_000,
        end=midnight_today - 10_000 + 1200,
    )
    db_session.commit()

    response = client.get("/v1.0/m8flow/home-stats", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["active_process_instances"] == 1
    assert body["errors_needing_review"] == 1
    assert body["completed_today"] == 1
    # avg of 600s and 1200s = 900s = 15.0 minutes, across both completed instances.
    assert body["avg_completion_minutes"] == 15.0


def test_super_admin_all_tenants_scope_and_explicit_tenant_id_override(client, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    ensure_v1_role(db_session, tenant_id="t2", role_name="user", user_ids=(user.id,))
    _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="running")
    _seed_instance(db_session, tenant_id="t2", initiator_id=user.id, status="running")
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    all_tenants = client.get("/v1.0/m8flow/home-stats", headers=headers)
    assert all_tenants.get_json()["active_process_instances"] == 2

    scoped = client.get("/v1.0/m8flow/home-stats?tenantId=t2", headers=headers)
    assert scoped.get_json()["active_process_instances"] == 1


def test_editor_sees_recent_instances_newest_first_with_projected_fields(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    older = _seed_instance(
        db_session, tenant_id="t1", initiator_id=user.id, status="complete", start=1_700_000_000
    )
    newer = _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        status="user_input_required",
        start=1_700_000_100,
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/home-recent-instances", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 2
    assert body[0]["id"] == newer.id
    assert body[1]["id"] == older.id
    assert body[0]["tenant_id"] == "t1"
    assert body[0]["tenant_name"] == "t1"
    assert body[0]["process_model_display_name"] == "Test Model"
    assert body[0]["start_in_seconds"] == 1_700_000_100
    assert body[0]["status"] == "user_input_required"
    assert set(body[0].keys()) == {
        "id",
        "tenant_id",
        "tenant_name",
        "process_model_display_name",
        "start_in_seconds",
        "status",
    }


def test_reviewer_gets_empty_recent_instances_not_403(client, db_session):
    user, token = _login_user(
        client, db_session, username="reviewer", groups=["t1:reviewer"], tenant_id="t1"
    )
    _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="running")
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/home-recent-instances", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.get_json() == []


def test_super_admin_recent_instances_all_tenants_and_tenant_id_override(client, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", name="Tenant Two", slug="t2")
    ensure_v1_role(db_session, tenant_id="t2", role_name="user", user_ids=(user.id,))
    t1_row = _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="error")
    t2_row = _seed_instance(db_session, tenant_id="t2", initiator_id=user.id, status="complete")
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    all_tenants = client.get("/v1.0/m8flow/home-recent-instances", headers=headers)
    assert all_tenants.status_code == 200
    ids = {row["id"] for row in all_tenants.get_json()}
    assert ids == {t1_row.id, t2_row.id}

    scoped = client.get("/v1.0/m8flow/home-recent-instances?tenantId=t2", headers=headers)
    scoped_body = scoped.get_json()
    assert len(scoped_body) == 1
    assert scoped_body[0]["id"] == t2_row.id
    assert scoped_body[0]["tenant_name"] == "Tenant Two"


def test_recent_instances_limit_is_honored(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    for _ in range(5):
        _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="running")
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/home-recent-instances?limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert len(response.get_json()) == 2


def test_editor_sees_my_tasks_oldest_first_with_projected_fields(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="running")
    older = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=user.id,
        task_title="Older task",
        lane_name="finance",
        created_at=1_700_000_000,
    )
    newer = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=user.id,
        task_title="Newer task",
        lane_name="reviewers",
        created_at=1_700_000_100,
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/home-my-tasks", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 2
    # Oldest-first by id (matches GetPendingTasksQuery).
    assert body[0]["id"] == older.id
    assert body[1]["id"] == newer.id
    assert body[0]["task_title"] == "Older task"
    assert body[0]["task_name"] == "Approve"
    assert body[0]["tenant_id"] == "t1"
    assert body[0]["tenant_name"] == "t1"
    assert body[0]["lane_name"] == "finance"
    assert body[0]["created_at_in_seconds"] == 1_700_000_000
    assert body[0]["process_instance_id"] == instance.id
    assert set(body[0].keys()) == {
        "id",
        "task_title",
        "task_name",
        "tenant_id",
        "tenant_name",
        "lane_name",
        "created_at_in_seconds",
        "process_instance_id",
    }


def test_reviewer_sees_my_tasks(client, db_session):
    """Contrast with recent-instances: reviewer has task-read (m8flow.yml +
    fallback) but not process-instance-read -- my-tasks must populate for
    them the same way home-stats populates tasks_waiting_on_me.
    """
    user, token = _login_user(
        client, db_session, username="reviewer", groups=["t1:reviewer"], tenant_id="t1"
    )
    instance = _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="running")
    task = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=user.id,
        task_title="Review me",
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/home-my-tasks", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 1
    assert body[0]["id"] == task.id
    assert body[0]["task_title"] == "Review me"


def test_my_tasks_excludes_tasks_assigned_to_other_users(client, db_session):
    editor, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    other, _ = _login_user(
        client, db_session, username="other-editor", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(db_session, tenant_id="t1", initiator_id=editor.id, status="running")
    mine = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=editor.id,
        task_title="Mine",
    )
    _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=other.id,
        task_title="Theirs",
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/home-my-tasks", headers={"Authorization": f"Bearer {token}"}
    )
    body = response.get_json()
    assert [row["id"] for row in body] == [mine.id]
    assert body[0]["task_title"] == "Mine"


def test_super_admin_my_tasks_all_tenants_and_tenant_id_override(client, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", name="Tenant Two", slug="t2")
    ensure_v1_role(db_session, tenant_id="t2", role_name="user", user_ids=(user.id,))
    t1_instance = _seed_instance(db_session, tenant_id="t1", initiator_id=user.id, status="running")
    t2_instance = _seed_instance(db_session, tenant_id="t2", initiator_id=user.id, status="running")
    t1_task = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=t1_instance.id,
        assignee_user_id=user.id,
        task_title="T1 task",
    )
    t2_task = _seed_pending_task(
        db_session,
        tenant_id="t2",
        process_instance_id=t2_instance.id,
        assignee_user_id=user.id,
        task_title="T2 task",
        lane_name="approvers",
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    all_tenants = client.get("/v1.0/m8flow/home-my-tasks", headers=headers)
    assert {row["id"] for row in all_tenants.get_json()} == {t1_task.id, t2_task.id}

    scoped = client.get("/v1.0/m8flow/home-my-tasks?tenantId=t2", headers=headers)
    scoped_body = scoped.get_json()
    assert len(scoped_body) == 1
    assert scoped_body[0]["id"] == t2_task.id
    assert scoped_body[0]["tenant_name"] == "Tenant Two"
