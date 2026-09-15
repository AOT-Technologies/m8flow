from __future__ import annotations

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, import_yaml, sync_groups
from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, VerifiedClaims
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME


class _ThinTokenProvider:
    def verify_token(self, token: str) -> VerifiedClaims:
        del token
        return VerifiedClaims(
            subject="editor-sub",
            issuer="https://example.test/realms/m8flow",
            username="editor",
            email="editor@example.test",
            roles=["editor"],
            memberships=[],
            jwt_claims={},
        )

    def list_memberships(self, *, username: str) -> list[Membership]:
        assert username == "editor"
        return [
            Membership(
                tenant_ref=TenantRef(id="t1", alias="m8flow", name="m8flow"),
                roles=["editor"],
                groups=["editor"],
            )
        ]


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
    import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user, token


class _ActiveOrgTokenProvider:
    """Since ticket 09 the token's `organization` claim carries only the single
    *active* org, so verify_token yields one membership -- but the endpoint must
    still surface the full list from the directory (both orgs), or a multi-org
    user loses the ability to switch."""

    def verify_token(self, token: str) -> VerifiedClaims:
        del token
        return VerifiedClaims(
            subject="editor-sub",
            issuer="https://example.test/realms/m8flow",
            username="editor",
            email="editor@example.test",
            roles=["editor"],
            memberships=[
                Membership(
                    tenant_ref=TenantRef(id="t1", alias="m8flow", name="m8flow"),
                    roles=["editor"],
                    groups=["editor"],
                )
            ],
            jwt_claims={},
        )

    def list_memberships(self, *, username: str) -> list[Membership]:
        assert username == "editor"
        return [
            Membership(tenant_ref=TenantRef(id="t1", alias="m8flow", name="m8flow"), roles=["editor"], groups=["editor"]),
            Membership(
                tenant_ref=TenantRef(id="t2", alias="second-org", name="Second Org"),
                roles=["editor"],
                groups=["editor"],
            ),
        ]


def test_organization_memberships_lists_all_orgs_even_when_token_carries_only_active(client, monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.routes.keycloak_controller.get_auth_provider",
        lambda: _ActiveOrgTokenProvider(),
    )
    client.set_cookie("access_token", "active-org-token")

    response = client.get("/v1.0/m8flow/organization-memberships")
    assert response.status_code == 200
    aliases = [org["alias"] for org in response.get_json()["organizations"]]
    assert aliases == ["m8flow", "second-org"]  # full directory list, not just the active org


def test_organization_memberships_enriches_when_token_omits_orgs(client, monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.routes.keycloak_controller.get_auth_provider",
        lambda: _ThinTokenProvider(),
    )
    client.set_cookie("access_token", "thin-token")

    response = client.get("/v1.0/m8flow/organization-memberships")
    assert response.status_code == 200
    body = response.get_json()
    assert body["organizations"] == [
        {"alias": "m8flow", "id": "t1", "name": "m8flow"},
    ]


def test_tenant_member_routes_authenticate_even_on_tenant_exempt_prefix(client, db_session):
    _user, token = _login_user(
        client, db_session, username="tenant-admin", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    # Cookie from _login_user may remain; unauthenticated callers must still
    # get 401 (not 400 tenant_override_forbidden from a leftover cookie).
    anonymous = client.get("/v1.0/m8flow/tenants/t1/members")
    assert anonymous.status_code == 401

    authed = client.get(
        "/v1.0/m8flow/tenants/t1/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert authed.status_code != 401
