"""Connexion request validation surfaces in the app's {error_code, message} shape.

Connexion routes + validates at the ASGI layer before Flask, so its validation
errors never reach the Flask error handlers. register_connexion_error_handlers
maps Connexion's ProblemException to the same JSON shape the rest of the API
uses. These tests exercise both a parameter failure (no auth needed) and a body
failure (the only /m8flow op with a required JSON body)."""
from __future__ import annotations

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME


def test_missing_required_query_param_maps_to_error_code(client):
    # GET /tenant-login-url declares `tenant` as a required query param and is
    # unauthenticated (security: []), so omitting it triggers Connexion
    # validation without any auth setup.
    response = client.get("/v1.0/m8flow/tenant-login-url")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    payload = response.get_json()
    assert set(payload) == {"error_code", "message"}
    assert payload["error_code"] == "bad_request"
    assert "tenant" in payload["message"]


def test_malformed_request_body_maps_to_error_code(client, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(
        db_session,
        username="super-admin",
        service="https://example.test/realms/m8flow",
        service_id="super-admin",
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=["super-admin"], tenant_id="t1")
    ensure_v1_role(db_session, tenant_id="t1", role_name="user", user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")

    # PUT /tenants/{tenant_id} requires a JSON body with `name`; Connexion
    # rejects the missing field before the controller runs.
    response = client.put(
        "/v1.0/m8flow/tenants/t1",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    payload = response.get_json()
    assert set(payload) == {"error_code", "message"}
    assert payload["error_code"] == "bad_request"
    assert "name" in payload["message"]
