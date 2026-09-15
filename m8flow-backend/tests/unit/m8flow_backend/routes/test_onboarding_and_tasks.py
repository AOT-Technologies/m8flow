from __future__ import annotations

import time

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.authorization import allow_uri
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, VerifiedClaims
from m8flow_backend.integrations.auth.base.roles import SUPER_ADMIN_ROLE
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


def test_editor_onboarding_and_tasks(client, db_session):
    _user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    headers = {"Authorization": f"Bearer {token}"}
    onboarding = client.get("/v1.0/onboarding", headers=headers)
    assert onboarding.status_code == 200
    tasks = client.get("/v1.0/tasks", headers=headers)
    assert tasks.status_code == 200


def test_reviewer_onboarding_and_tasks_multi_org(client, db_session):
    user, token = _login_user(
        client, db_session, username="reviewer", groups=["org-a:reviewer"], tenant_id="org-a"
    )
    headers = {"Authorization": f"Bearer {token}"}
    first = client.get("/v1.0/onboarding", headers=headers)
    assert first.status_code == 200

    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant_b = ensure_tenant(db_session, tenant_id="org-b", slug="org-b")
    ensure_membership(db_session, user, tenant_b)
    sync_groups(db_session, user=user, group_identifiers=["org-b:reviewer"], tenant_id="org-b")
    ensure_v1_role(db_session, tenant_id="org-b", role_name="user", user_ids=(user.id,))
    db_session.commit()
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "org-b")
    second = client.get("/v1.0/onboarding", headers=headers)
    assert second.status_code == 200
    assert second.get_json()["tenant_id"] == "org-b"
    tasks = client.get("/v1.0/tasks", headers=headers)
    assert tasks.status_code == 200


def test_status_is_public(client):
    response = client.get("/v1.0/status")
    assert response.status_code == 200


def test_allow_uri_short_circuits_on_verified_super_admin_role(app, db_session):
    user = ensure_user(
        db_session,
        username="root",
        service="https://example.test/realms/master",
        service_id="root",
    )
    db_session.commit()
    with app.test_request_context("/v1.0/onboarding"):
        from flask import g

        g.verified_claims = VerifiedClaims(
            subject="root",
            issuer="https://example.test/realms/master",
            username="root",
            roles=[SUPER_ADMIN_ROLE],
        )
        assert allow_uri(user, "GET", "/v1.0/onboarding", session=db_session) is True


def test_allow_uri_does_not_elevate_a_different_actor_from_request_claims(app, db_session):
    ensure_user(
        db_session,
        username="root",
        service="https://example.test/realms/master",
        service_id="root",
    )
    editor = ensure_user(
        db_session,
        username="editor",
        service="https://example.test/realms/m8flow",
        service_id="editor-1",
    )
    db_session.commit()
    with app.test_request_context("/v1.0/onboarding"):
        from flask import g

        g.verified_claims = VerifiedClaims(
            subject="root",
            issuer="https://example.test/realms/master",
            username="root",
            roles=[SUPER_ADMIN_ROLE],
        )
        assert allow_uri(editor, "GET", "/v1.0/onboarding", session=db_session) is False


class _ThinTokenProvider:
    issuer = "https://example.test/realms/m8flow"

    def verify_token(self, token: str) -> VerifiedClaims:
        del token
        return VerifiedClaims(
            subject="kc-editor-1",
            issuer=self.issuer,
            username="editor",
            roles=[],
            memberships=[
                Membership(tenant_ref=TenantRef(id="t1", alias="t1"), roles=[], groups=[]),
                Membership(tenant_ref=TenantRef(id="t2", alias="t2"), roles=[], groups=[]),
            ],
            jwt_claims={
                "sub": "kc-editor-1",
                "iss": self.issuer,
                "preferred_username": "editor",
            },
        )

    def list_memberships(self, *, username: str) -> list[Membership]:
        del username
        return [
            Membership(
                tenant_ref=TenantRef(id="t1", alias="t1"),
                roles=["editor"],
                groups=["editor"],
            ),
            Membership(
                tenant_ref=TenantRef(id="t2", alias="t2"),
                roles=["reviewer"],
                groups=["reviewer"],
            ),
        ]


def test_stale_shared_realm_user_thin_token_enriches_active_org_groups(
    client, db_session, monkeypatch
):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    issuer = _ThinTokenProvider.issuer
    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    user = ensure_user(
        db_session,
        username="editor",
        service=issuer,
        service_id="kc-editor-1",
    )
    ensure_membership(db_session, user, tenant)
    ensure_v1_role(db_session, tenant_id="t1", role_name="user", user_ids=(user.id,))
    db_session.commit()

    provider = _ThinTokenProvider()
    monkeypatch.setattr("m8flow_backend.integrations.auth.get_auth_provider", lambda: provider)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(
        {
            "sub": "kc-editor-1",
            "iss": issuer,
            "preferred_username": "editor",
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="RS256",
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")
    headers = {"Authorization": f"Bearer {token}"}

    onboarding = client.get("/v1.0/onboarding", headers=headers)
    assert onboarding.status_code == 200
    tasks = client.get("/v1.0/tasks", headers=headers)
    assert tasks.status_code == 200

    db_session.expire_all()
    db_session.refresh(user)
    identifiers = {getattr(group, "identifier", "") for group in user.groups}
    assert "t1:editor" in identifiers
    assert "t2:reviewer" not in identifiers
