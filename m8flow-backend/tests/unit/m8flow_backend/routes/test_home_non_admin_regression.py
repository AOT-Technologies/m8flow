"""Ticket 10 regression: non-admin shared-realm Home + onboarding/tasks.

Covers AGENTS.md's bar for this map's Home work:
- non-admin editor/reviewer (not only super-admin)
- GET /v1.0/onboarding + GET /v1.0/tasks
- multi-organization tenant cookie switch
- Home endpoints (stats / recent-instances / my-tasks) stay usable
"""

from __future__ import annotations

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME


def _login_user(client, db_session, *, username: str, groups: list[str], tenant_id: str):
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


def _assert_home_bundle_ok(client, headers, *, expect_instance_data: bool):
    """Home page's three data calls for a non-admin (no tenantId override)."""
    stats = client.get("/v1.0/m8flow/home-stats", headers=headers)
    assert stats.status_code == 200
    body = stats.get_json()
    assert body["total_tenants"] is None  # super-admin-only
    if expect_instance_data:
        assert body["active_process_instances"] is not None
    else:
        assert body["active_process_instances"] is None
    assert body["tasks_waiting_on_me"] is not None

    recent = client.get("/v1.0/m8flow/home-recent-instances", headers=headers)
    assert recent.status_code == 200
    assert isinstance(recent.get_json(), list)
    if not expect_instance_data:
        assert recent.get_json() == []

    my_tasks = client.get("/v1.0/m8flow/home-my-tasks", headers=headers)
    assert my_tasks.status_code == 200
    assert isinstance(my_tasks.get_json(), list)


def test_editor_onboarding_tasks_and_home_bundle(client, db_session):
    _user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200
    _assert_home_bundle_ok(client, headers, expect_instance_data=True)


def test_reviewer_onboarding_tasks_and_home_bundle(client, db_session):
    _user, token = _login_user(
        client, db_session, username="reviewer", groups=["t1:reviewer"], tenant_id="t1"
    )
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200
    # reviewer: task-read yes, process-instance-read no (m8flow.yml)
    _assert_home_bundle_ok(client, headers, expect_instance_data=False)


def test_editor_multi_org_home_after_tenant_cookie_switch(client, db_session):
    """Multi-organization case: join a second org, finalize via cookie, Home still works."""
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    user, token = _login_user(
        client, db_session, username="editor-multi", groups=["org-a:editor"], tenant_id="org-a"
    )
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    _assert_home_bundle_ok(client, headers, expect_instance_data=True)

    tenant_b = ensure_tenant(db_session, tenant_id="org-b", slug="org-b")
    ensure_membership(db_session, user, tenant_b)
    sync_groups(db_session, user=user, group_identifiers=["org-b:editor"], tenant_id="org-b")
    ensure_v1_role(db_session, tenant_id="org-b", role_name="user", user_ids=(user.id,))
    db_session.commit()

    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "org-b")
    onboarding = client.get("/v1.0/onboarding", headers=headers)
    assert onboarding.status_code == 200
    assert onboarding.get_json()["tenant_id"] == "org-b"
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200
    _assert_home_bundle_ok(client, headers, expect_instance_data=True)

    # Non-admin must not get cross-tenant override via tenantId query param.
    scoped = client.get("/v1.0/m8flow/home-stats?tenantId=org-a", headers=headers)
    assert scoped.status_code == 200
    # Still scoped to cookie tenant (org-b); total_tenants stays null.
    assert scoped.get_json()["total_tenants"] is None
