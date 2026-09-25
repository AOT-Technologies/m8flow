"""POST /m8flow/nats-tokens stores keys under the canonical tenant row id.

Regression: ``require_tenant_id`` returns the raw ``m8flow_selected_tenant`` cookie,
so a key created with a Keycloak organization UUID in that cookie was stored under a
tenant that does not exist; the trigger route then failed with tenant_slug_unresolved.
"""

from __future__ import annotations

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


def test_org_uuid_from_the_bearer_token_maps_to_the_tenant_row(app, db_session, monkeypatch):
    # No cookie: the tenant bound from the token is the Keycloak org UUID, which only
    # maps to a tenant through the token's own organization alias.
    ensure_tenant(db_session, tenant_id="t-acme", slug="acme")
    db_session.commit()
    monkeypatch.setattr(nats_token_controller, "require_tenant_id", lambda _user: ORG_UUID)

    with app.test_request_context("/v1.0/m8flow/nats-tokens"):
        g.db_session = db_session
        g.verified_claims = _claims(Membership(tenant_ref=TenantRef(id=ORG_UUID, alias="acme")))
        assert nats_token_controller._require_known_tenant_id(object()) == "t-acme"
        assert g.m8flow_tenant_id == "t-acme"


def test_org_uuid_not_in_the_callers_token_is_rejected(app, db_session, monkeypatch):
    ensure_tenant(db_session, tenant_id="t-acme", slug="acme")
    db_session.commit()
    org_uuid = ORG_UUID
    monkeypatch.setattr(nats_token_controller, "require_tenant_id", lambda _user: org_uuid)

    with app.test_request_context("/v1.0/m8flow/nats-tokens"):
        g.db_session = db_session
        # The token belongs to a different organization: no mapping, no access widening.
        g.verified_claims = _claims(Membership(tenant_ref=TenantRef(id="other-org", alias="other")))
        with pytest.raises(ApiError) as exc:
            nats_token_controller._require_known_tenant_id(object())

    assert exc.value.status_code == 400
    assert exc.value.error_code == "tenant_not_found"
    assert org_uuid in exc.value.message
