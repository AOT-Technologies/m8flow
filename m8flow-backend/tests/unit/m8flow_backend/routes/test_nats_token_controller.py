"""POST /m8flow/nats-tokens stores keys under the canonical tenant row id.

Regression: ``require_tenant_id`` returns the raw ``m8flow_selected_tenant`` cookie,
so a key created with a Keycloak organization UUID in that cookie was stored under a
tenant that does not exist; the trigger route then failed with tenant_slug_unresolved.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import g
from sqlalchemy import select

from m8flow_backend import identity
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.errors import ApiError
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, VerifiedClaims
from m8flow_backend.models import M8flowNatsApiKeyModel
from m8flow_backend.routes import nats_token_controller

_SERVICE = "https://example.test/realms/m8flow"


def _tenant_admin(db_session, *, tenant_id: str, slug: str):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=slug)
    user = ensure_user(db_session, username="tadmin", service=_SERVICE, service_id="tadmin")
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=[f"{tenant_id}:tenant-admin"], tenant_id=tenant_id)
    identity.import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    db_session.refresh(user)
    return user


def test_key_selected_by_slug_is_stored_under_the_tenant_row_id(client, db_session):
    user = _tenant_admin(db_session, tenant_id="t-acme", slug="acme")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "acme")

    response = client.post(
        "/v1.0/m8flow/nats-tokens",
        json={"label": "ci", "expiresInDays": 30, "scope": ["group-a/flow-a"]},
        headers={"Authorization": f"Bearer {encode_auth_token(user=user)}"},
    )

    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    assert body["tenantId"] == "t-acme"
    assert body["token"].startswith(f"m8f_{body['id']}.")
    db_session.expire_all()
    stored = db_session.scalars(select(M8flowNatsApiKeyModel)).one()
    assert (stored.m8f_tenant_id, stored.scope) == ("t-acme", "group-a/flow-a")


ORG_UUID = "5da23392-2e02-4aa3-96b2-0d16a29dfe78"


def _claims(*memberships: Membership) -> VerifiedClaims:
    return VerifiedClaims(
        subject="user-1",
        issuer="https://example.test/realms/m8flow",
        active_tenant_ref=memberships[0].tenant_ref if memberships else None,
        memberships=list(memberships),
    )


def _non_admin():
    return SimpleNamespace(groups=[], service_id=None, username=None)


def test_org_uuid_from_the_bearer_token_maps_to_the_tenant_row(app, db_session):
    # No cookie: the tenant bound from the token is the Keycloak org UUID, which only
    # maps to a tenant through the token's own organization alias.
    ensure_tenant(db_session, tenant_id="t-acme", slug="acme")
    db_session.commit()

    with app.test_request_context("/v1.0/m8flow/nats-tokens"):
        g.db_session = db_session
        g.m8flow_tenant_id = ORG_UUID
        g.verified_claims = _claims(Membership(tenant_ref=TenantRef(id=ORG_UUID, alias="acme")))
        assert nats_token_controller._require_known_tenant_id(_non_admin()) == "t-acme"
        assert g.m8flow_tenant_id == "t-acme"


def test_org_uuid_not_in_the_callers_token_is_rejected(app, db_session):
    ensure_tenant(db_session, tenant_id="t-acme", slug="acme")
    db_session.commit()

    with app.test_request_context("/v1.0/m8flow/nats-tokens"):
        g.db_session = db_session
        g.m8flow_tenant_id = ORG_UUID
        # The token belongs to a different organization: no mapping, no access widening.
        g.verified_claims = _claims(Membership(tenant_ref=TenantRef(id="other-org", alias="other")))
        with pytest.raises(ApiError) as exc:
            nats_token_controller._require_known_tenant_id(_non_admin())

    assert exc.value.status_code == 400
    assert exc.value.error_code == "tenant_not_found"
    assert ORG_UUID in exc.value.message


def test_a_tenant_admin_elsewhere_cannot_mint_keys_as_an_editor(client, db_session):
    user = _tenant_admin(db_session, tenant_id="t1", slug="t1")
    tenant = ensure_tenant(db_session, tenant_id="t2", slug="t2")
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=["t2:editor"], tenant_id="t2")
    identity.import_yaml(db_session, tenant_id="t2")
    db_session.commit()
    db_session.refresh(user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t2")

    response = client.post(
        "/v1.0/m8flow/nats-tokens",
        json={"label": "sneaky"},
        headers={"Authorization": f"Bearer {encode_auth_token(user=user)}"},
    )

    assert response.status_code == 403, response.get_json()
    assert db_session.scalars(select(M8flowNatsApiKeyModel)).all() == []


def _member(db_session, role: str):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id="t-acme", slug="acme")
    user = ensure_user(db_session, username=f"u-{role}", service=_SERVICE, service_id=f"u-{role}")
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=[f"t-acme:{role}"], tenant_id="t-acme")
    identity.import_yaml(db_session, tenant_id="t-acme")
    ensure_v1_role(db_session, tenant_id="t-acme", role_name="user", user_ids=(user.id,))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.mark.parametrize("role", ["editor", "reviewer"])
def test_only_tenant_admins_manage_keys(client, db_session, role):
    user = _member(db_session, role)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t-acme")
    headers = {"Authorization": f"Bearer {encode_auth_token(user=user)}"}

    assert client.post("/v1.0/m8flow/nats-tokens", json={"label": "x"}, headers=headers).status_code == 403
    assert client.get("/v1.0/m8flow/nats-tokens", headers=headers).status_code == 403
    assert client.delete("/v1.0/m8flow/nats-tokens/abc", headers=headers).status_code == 403
    assert db_session.scalars(select(M8flowNatsApiKeyModel)).all() == []


def test_a_tenant_admin_lists_and_revokes_keys(client, db_session):
    user = _tenant_admin(db_session, tenant_id="t-acme", slug="acme")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t-acme")
    headers = {"Authorization": f"Bearer {encode_auth_token(user=user)}"}
    key_id = client.post("/v1.0/m8flow/nats-tokens", json={"label": "ci"}, headers=headers).get_json()["id"]

    listed = client.get("/v1.0/m8flow/nats-tokens", headers=headers)
    assert listed.status_code == 200
    assert [key["id"] for key in listed.get_json()["keys"]] == [key_id]
    revoked = client.delete(f"/v1.0/m8flow/nats-tokens/{key_id}", headers=headers)
    assert (revoked.status_code, revoked.get_json()["revoked"]) == (200, True)
