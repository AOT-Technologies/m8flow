"""NATS monitoring access, end to end. READ ONLY throughout.

Locks in:
- every route, event history included, is super-admin only; tenant-admin,
  editor and reviewer stay out of every route;
- the wildcard does not reach ``/m8flow/nats-tokens``, whose tenant-admin grants are unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from m8flow_backend import identity
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.authorization import allow_uri
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups

_SRC = Path(__file__).resolve().parents[4] / "src" / "m8flow_backend"
_SERVICE = "https://example.test/realms/m8flow"


def _permissions() -> dict:
    return yaml.safe_load((_SRC / "config" / "permissions" / "m8flow.yml").read_text(encoding="utf-8"))["permissions"]


def _nats_routes() -> list[str]:
    spec = yaml.safe_load((_SRC / "api.yml").read_text(encoding="utf-8"))
    return sorted(
        "/v1.0/m8flow" + re.sub(r"\{[^}]+\}", "1", path) for path in spec["paths"] if path.startswith("/nats/")
    )


NATS_ROUTES = _nats_routes()


def test_all_seven_monitoring_routes_are_declared():
    assert len(NATS_ROUTES) == 7


def test_nats_monitoring_is_one_super_admin_grant():
    grants = {name: p for name, p in _permissions().items() if str(p.get("uri", "")).startswith("/m8flow/nats/")}
    assert grants == {
        "read-nats-monitoring": {"groups": ["super-admin"], "actions": ["read"], "uri": "/m8flow/nats/*"},
    }

def test_nats_token_grants_are_unchanged():
    perms = _permissions()
    assert perms["manage-nats-tokens"]["groups"] == ["tenant-admin"]
    assert perms["manage-nats-tokens-by-id"]["groups"] == ["tenant-admin"]
    assert set(perms["read-nats-tokens"]["groups"]) == {"tenant-admin", "super-admin"}


def _provision(db_session, *, username: str, groups: list[str], tenant_id: str = "t1"):
    from m8flow_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(db_session, username=username, service=_SERVICE, service_id=username)
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    identity.import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(user)
    return user


def _headers(client, user, *, tenant_id: str = "t1"):
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return {"Authorization": f"Bearer {encode_auth_token(user=user)}"}


@pytest.mark.parametrize("path", NATS_ROUTES)
def test_unauthenticated_is_401(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("role", ["tenant-admin", "editor", "reviewer"])
def test_tenant_roles_are_forbidden_on_every_route(client, db_session, role):
    user = _provision(db_session, username=f"u-{role}", groups=[f"t1:{role}"])
    headers = _headers(client, user)
    for path in NATS_ROUTES:
        response = client.get(path, headers=headers)
        assert response.status_code == 403, (role, path, response.get_json())
        assert response.get_json()["error_code"] == "permission_denied", (role, path)


def test_super_admin_passes_the_gate_on_every_route(client, db_session):
    user = _provision(db_session, username="root", groups=["super-admin"])
    headers = _headers(client, user)
    for path in NATS_ROUTES:
        # Monitoring/inspection are disabled in unit tests (503 / 403
        # nats_message_inspection_disabled) and the sample event id is unknown (404);
        # none of those is an authorization denial.
        response = client.get(path, headers=headers)
        assert response.status_code != 401, path
        assert response.get_json().get("error_code") not in ("permission_denied", "forbidden"), path


def test_super_admin_reads_cross_tenant_event_history(client, db_session):
    user = _provision(db_session, username="root", groups=["super-admin"])
    response = client.get("/v1.0/m8flow/nats/events?allTenants=true", headers=_headers(client, user))
    assert response.status_code == 200
    assert response.get_json()["pagination"]["total"] == 0
    # Static /events/summary must not be captured by /events/{event_id}.
    summary = client.get("/v1.0/m8flow/nats/events/summary?allTenants=true", headers=_headers(client, user))
    assert summary.status_code == 200
    assert summary.get_json()["total"] == 0


def test_wildcard_does_not_reach_nats_tokens(db_session):
    tenant_admin = _provision(db_session, username="tadmin", groups=["t1:tenant-admin"])
    assert allow_uri(tenant_admin, "GET", "/v1.0/m8flow/nats-tokens", session=db_session) is True
    assert allow_uri(tenant_admin, "GET", "/v1.0/m8flow/nats/streams", session=db_session, group_fallback=False) is False


def test_permissions_check_matches_what_the_routes_enforce(client, db_session):
    """The designer shows the NATS page from POST /permissions-check. It must not report
    access via the tenant-admin group fallback that the routes turn off."""
    user = _provision(db_session, username="tadmin", groups=["t1:tenant-admin"])
    response = client.post(
        "/v1.0/permissions-check",
        json={"requests_to_check": {"/m8flow/nats/streams": ["GET"], "/m8flow/nats/events": ["GET"]}},
        headers=_headers(client, user),
    )

    assert response.status_code == 200
    results = response.get_json()["results"]
    assert results["/m8flow/nats/streams"]["GET"] is False
    assert results["/m8flow/nats/events"]["GET"] is False



def _multi_org_user(db_session):
    """Tenant-admin in t1 but only an editor in t2: a role in one organization must not
    carry into another."""
    _provision(db_session, username="multi", groups=["t1:tenant-admin"], tenant_id="t1")
    return _provision(db_session, username="multi", groups=["t2:editor"], tenant_id="t2")


def _switch_to(client, db_session, user, tenant_id: str):
    """What tenant selection does: re-point the membership, then send the cookie."""
    ensure_membership(db_session, user, ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id))
    db_session.commit()
    return _headers(client, user, tenant_id=tenant_id)


@pytest.mark.parametrize("tenant_id", ["t1", "t2"])
def test_multi_org_user_is_denied_nats_in_either_tenant(client, db_session, tenant_id):
    user = _multi_org_user(db_session)
    headers = _switch_to(client, db_session, user, tenant_id)
    check = {"requests_to_check": {"/m8flow/nats/streams": ["GET"], "/m8flow/nats/events": ["GET"]}}

    assert client.get("/v1.0/m8flow/nats/events", headers=headers).status_code == 403
    results = client.post("/v1.0/permissions-check", json=check, headers=headers).get_json()["results"]
    assert results["/m8flow/nats/streams"]["GET"] is False
    assert results["/m8flow/nats/events"]["GET"] is False


@pytest.mark.parametrize("tenant_id", ["t1", "t2"])
def test_multi_org_user_keeps_onboarding_and_tasks_in_either_tenant(client, db_session, tenant_id):
    # AGENTS.md minimum non-admin regression, multi-organization case.
    user = _multi_org_user(db_session)
    headers = _switch_to(client, db_session, user, tenant_id)

    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200
