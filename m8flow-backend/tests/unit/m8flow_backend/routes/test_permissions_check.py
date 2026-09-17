from __future__ import annotations

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.integrations.auth.base.roles import SUPER_ADMIN_ROLE


def _super_admin_headers(client, db_session):
    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(
        db_session,
        username="permissions-check-admin",
        service="https://example.test/realms/m8flow",
        service_id="permissions-check-admin",
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=[SUPER_ADMIN_ROLE], tenant_id="t1")
    db_session.commit()
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")
    return {"Authorization": f"Bearer {encode_auth_token(user=user)}"}


def test_permissions_check_normalizes_mixed_case_methods(client, db_session):
    headers = _super_admin_headers(client, db_session)

    response = client.post(
        "/v1.0/permissions-check",
        headers=headers,
        json={"requests_to_check": {"/v1.0/onboarding": ["gEt"]}},
    )

    assert response.status_code == 200
    assert response.get_json()["results"] == {"/v1.0/onboarding": {"GET": True}}


def test_permissions_check_denies_unsupported_methods_without_calling_authorizer(client, db_session):
    headers = _super_admin_headers(client, db_session)

    response = client.post(
        "/v1.0/permissions-check",
        headers=headers,
        json={"requests_to_check": {"/v1.0/onboarding": ["OPTIONS", "TRACE", "read"]}},
    )

    assert response.status_code == 200
    assert response.get_json()["results"] == {
        "/v1.0/onboarding": {"OPTIONS": False, "TRACE": False, "READ": False}
    }
