"""Regression coverage for closing the v1.py routes that authenticated but
never checked permission (architecture review follow-up to the
`@require_permission` decorator introduced in authorization/decorators.py).

Each of these routes now has an m8flow.yml-backed grant boundary: a role the
YAML explicitly lists should pass, and a role it omits should still be
denied. Assertions against `_uri_permitted` directly (the
`test_multi_org_db_grants.py` pattern) prove the real DB-grant boundary,
since editor/tenant-admin are covered unconditionally by
`_group_identifier_fallback` and can't tell a real grant from that escape
hatch. Route-level `client` calls on top of that prove `@require_permission`
is actually wired into the route, not just that the underlying grant exists.

`start_process` (POST /v1.0/process-instances) and `submit_external_form`
(POST /v1.0/m8flow/external-forms/*) are deliberately not covered here --
see the comments left in routes/v1.py at those two routes for why they were
left ungated.

claim_task/complete_task have no route-level HTTP deny test, unlike the
other routes below: `_provision_tenant_role` calls `ensure_v1_role(...,
role_name="user")` so the command layer (`ClaimTaskCommand`/
`CompleteTaskCommand`) doesn't also 403 for an unrelated reason, but that
puts every provisioned test user in a "t1:user" group --
`_group_identifier_fallback`'s loose `"/tasks" in path` substring match then
lets *any* such user claim/complete via the fallback regardless of their
real YAML role, an artifact of this test harness (real logins never sync a
"user" YAML role, only the six in VALID_TENANT_ROLE_NAMES). The
`_uri_permitted` assertions below aren't affected -- they check the DB-grant
layer directly, before the fallback ever runs -- so they remain the
authoritative proof for those two routes' deny boundary.
"""

from __future__ import annotations

from m8flow_backend import identity
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.authorization import _uri_permitted
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

_TENANT_ID = "t1"
_SERVICE = "https://example.test/realms/m8flow"


def _provision_tenant_role(db_session, *, username: str, group_name: str):
    """Mirrors a real login for a tenant role: membership, tenant-qualified
    group sync, m8flow.yml grants materialized into the DB, and a v1_role so
    command-layer authorization (a separate check `workflow.claim`/`complete`
    go through) doesn't also deny these requests for an unrelated reason.
    """
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=_TENANT_ID, slug=_TENANT_ID)
    user = ensure_user(db_session, username=username, service=_SERVICE, service_id=username)
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=[f"{_TENANT_ID}:{group_name}"], tenant_id=_TENANT_ID)
    identity.import_yaml(db_session, tenant_id=_TENANT_ID)
    ensure_v1_role(db_session, tenant_id=_TENANT_ID, role_name="user", user_ids=(user.id,))
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(user)
    return user


def _headers(user):
    return {"Authorization": f"Bearer {encode_auth_token(user=user)}"}


# -- Grant-boundary assertions (allow_uri / _uri_permitted directly) --------


def test_manage_tasks_grants_reviewer_and_submitter_claim_and_complete(db_session):
    for group_name in ("reviewer", "submitter"):
        user = _provision_tenant_role(db_session, username=f"{group_name}-manage", group_name=group_name)
        assert _uri_permitted(db_session, user, "update", "/tasks/1/claim") is True
        assert _uri_permitted(db_session, user, "create", "/tasks/1/complete") is True


def test_manage_tasks_denies_integrator_claim_and_complete(db_session):
    user = _provision_tenant_role(db_session, username="integrator-manage", group_name="integrator")
    assert _uri_permitted(db_session, user, "update", "/tasks/1/claim") is False
    assert _uri_permitted(db_session, user, "create", "/tasks/1/complete") is False


def test_read_tasks_grants_viewer_get_task_but_not_claim(db_session):
    user = _provision_tenant_role(db_session, username="viewer-get-task", group_name="viewer")
    assert _uri_permitted(db_session, user, "read", "/tasks/1") is True
    assert _uri_permitted(db_session, user, "update", "/tasks/1/claim") is False


def test_read_process_model_list_grants_viewer_but_not_reviewer(db_session):
    viewer = _provision_tenant_role(db_session, username="viewer-pm-list", group_name="viewer")
    reviewer = _provision_tenant_role(db_session, username="reviewer-pm-list", group_name="reviewer")
    assert _uri_permitted(db_session, viewer, "read", "/process-models") is True
    assert _uri_permitted(db_session, reviewer, "read", "/process-models") is False


def test_no_grant_matches_viewer_save_process_model(db_session):
    """PM:ALL only expands to /process-models/%, which never matches the bare
    /process-models create endpoint -- so even a role otherwise broad like
    viewer has no real grant to save a process model."""
    user = _provision_tenant_role(db_session, username="viewer-save-pm", group_name="viewer")
    assert _uri_permitted(db_session, user, "create", "/process-models") is False


def test_read_process_instance_list_grants_viewer_but_not_reviewer(db_session):
    viewer = _provision_tenant_role(db_session, username="viewer-pi-list", group_name="viewer")
    reviewer = _provision_tenant_role(db_session, username="reviewer-pi-list", group_name="reviewer")
    assert _uri_permitted(db_session, viewer, "read", "/process-instances") is True
    assert _uri_permitted(db_session, reviewer, "read", "/process-instances") is False


def test_read_secrets_grants_integrator_but_not_editor_or_reviewer(db_session):
    integrator = _provision_tenant_role(db_session, username="integrator-secrets", group_name="integrator")
    reviewer = _provision_tenant_role(db_session, username="reviewer-secrets", group_name="reviewer")
    assert _uri_permitted(db_session, integrator, "read", "/secrets") is True
    assert _uri_permitted(db_session, reviewer, "read", "/secrets") is False


def test_manage_secret_items_grants_integrator_but_not_viewer(db_session):
    integrator = _provision_tenant_role(db_session, username="integrator-put-secret", group_name="integrator")
    viewer = _provision_tenant_role(db_session, username="viewer-put-secret", group_name="viewer")
    assert _uri_permitted(db_session, integrator, "update", "/secrets/api-key") is True
    assert _uri_permitted(db_session, viewer, "update", "/secrets/api-key") is False


# -- Route-level wiring: prove @require_permission is actually applied ------


def test_claim_task_route_lets_reviewer_reach_the_command(client, db_session):
    """A granted role must not be blocked at the permission gate -- the 999999
    id doesn't exist, so this should fail downstream (not-found from the
    command layer), never with permission_denied."""
    user = _provision_tenant_role(db_session, username="reviewer-claim-route", group_name="reviewer")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, _TENANT_ID)
    response = client.put("/v1.0/tasks/999999/claim", headers=_headers(user))
    assert response.status_code != 403
    assert response.get_json()["error_code"] != "permission_denied"


def test_list_process_models_route_hides_denial_as_empty_list(client, db_session):
    user = _provision_tenant_role(db_session, username="reviewer-list-pm-route", group_name="reviewer")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, _TENANT_ID)
    response = client.get("/v1.0/process-models", headers=_headers(user))
    assert response.status_code == 200
    assert response.get_json() == []


def test_list_secrets_route_hides_denial_as_empty_list(client, db_session):
    user = _provision_tenant_role(db_session, username="reviewer-list-secrets-route", group_name="reviewer")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, _TENANT_ID)
    response = client.get("/v1.0/secrets", headers=_headers(user))
    assert response.status_code == 200
    assert response.get_json() == {
        "results": [],
        "pagination": {"count": 0, "total": 0, "pages": 0},
    }


def test_put_secret_route_denies_viewer_with_403(client, db_session):
    user = _provision_tenant_role(db_session, username="viewer-put-secret-route", group_name="viewer")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, _TENANT_ID)
    response = client.put(
        "/v1.0/secrets/api-key", headers=_headers(user), json={"value": "shh"}
    )
    assert response.status_code == 403
    assert response.get_json()["error_code"] == "permission_denied"


def test_editor_still_reaches_all_eight_routes(client, db_session):
    """editor is covered unconditionally by _group_identifier_fallback, so
    this is a smoke test that the new gates didn't regress the one role
    every route already worked for -- not proof of a real per-route grant.
    Secrets writes are YAML-only (group_fallback=False), so editor PUT is 403.
    """
    user = _provision_tenant_role(db_session, username="editor-smoke", group_name="editor")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, _TENANT_ID)
    headers = _headers(user)

    assert client.get("/v1.0/process-models", headers=headers).status_code == 200
    assert client.get("/v1.0/process-instances", headers=headers).status_code == 200
    assert client.get("/v1.0/secrets", headers=headers).status_code == 200
    assert client.put("/v1.0/tasks/999999/claim", headers=headers).status_code != 403
    assert client.post("/v1.0/tasks/999999/complete", headers=headers, json={}).status_code != 403
    assert client.get("/v1.0/tasks/999999", headers=headers).status_code != 403
    assert client.post(
        "/v1.0/process-models", headers=headers, json={"path": "g:m", "xml": "<bpmn/>"}
    ).status_code != 403
    assert client.put("/v1.0/secrets/api-key", headers=headers, json={"value": "shh"}).status_code == 403
