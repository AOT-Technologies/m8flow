"""Celery monitoring and control access, end to end.

Locks in: every /m8flow/celery/* route is super-admin only; tenant-admin, editor and
reviewer stay out of reads and control actions alike, including through
POST /permissions-check, which drives the designer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from m8flow_backend import identity
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups

_SRC = Path(__file__).resolve().parents[4] / "src" / "m8flow_backend"
_SERVICE = "https://example.test/realms/m8flow"


def _spec() -> dict:
    return yaml.safe_load((_SRC / "api.yml").read_text(encoding="utf-8"))


def _celery_routes() -> list[tuple[str, str]]:
    return sorted(
        (method.upper(), "/v1.0/m8flow" + re.sub(r"\{[^}]+\}", "x", path))
        for path, operations in _spec()["paths"].items()
        if path.startswith("/celery/")
        for method in operations
    )


CELERY_ROUTES = _celery_routes()
READ_ROUTES = [route for route in CELERY_ROUTES if route[0] == "GET"]
CONTROL_ROUTES = [route for route in CELERY_ROUTES if route[0] == "POST"]


# Connexion validates a request body before the route's permission gate runs, so each
# control route gets a body that passes its schema; the permission layer is under test.
_VALID_BODIES = {
    "revoke": {"taskId": "t1"},
    "rate-limit": {"taskName": "m8flow.task"},
    "time-limit": {"taskName": "m8flow.task"},
    "x": {"action": "pool_grow"},
}


def _call(client, method: str, path: str, **kwargs):
    if method == "POST":
        return client.post(path, json=_VALID_BODIES[path.rsplit("/", 1)[-1]], **kwargs)
    return client.get(path, **kwargs)


def test_reads_are_get_and_controls_are_post_under_control():
    assert [path for _, path in READ_ROUTES] == [
        "/v1.0/m8flow/celery/broker",
        "/v1.0/m8flow/celery/history",
        "/v1.0/m8flow/celery/history/x",
        "/v1.0/m8flow/celery/overview",
        "/v1.0/m8flow/celery/task-types",
        "/v1.0/m8flow/celery/tasks",
        "/v1.0/m8flow/celery/workers",
    ]
    assert all("/celery/control/" in path for _, path in CONTROL_ROUTES)
    assert len(CONTROL_ROUTES) == 4


def test_grants_are_super_admin_only():
    permissions = yaml.safe_load((_SRC / "config" / "permissions" / "m8flow.yml").read_text(encoding="utf-8"))["permissions"]
    grants = {name: p for name, p in permissions.items() if str(p.get("uri", "")).startswith("/m8flow/celery")}
    assert grants == {
        "read-celery-monitoring": {"groups": ["super-admin"], "actions": ["read"], "uri": "/m8flow/celery/*"},
        "manage-celery-monitoring": {"groups": ["super-admin"], "actions": ["create"], "uri": "/m8flow/celery/control/*"},
    }


def _provision(db_session, *, username: str, groups: list[str], tenant_id: str = "t1"):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

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


@pytest.mark.parametrize("method,path", CELERY_ROUTES)
def test_unauthenticated_is_401(client, method, path):
    assert _call(client, method, path).status_code == 401


@pytest.mark.parametrize("role", ["editor", "reviewer", "tenant-admin"])
def test_tenant_roles_are_forbidden_on_every_route(client, db_session, role):
    user = _provision(db_session, username=f"u-{role}", groups=[f"t1:{role}"])
    headers = _headers(client, user)
    for method, path in CELERY_ROUTES:
        response = _call(client, method, path, headers=headers)
        assert response.status_code == 403, (role, method, path, response.get_json())
        assert response.get_json()["error_code"] == "permission_denied", (role, path)


def test_super_admin_passes_the_gate_on_every_route(client, db_session):
    user = _provision(db_session, username="root", groups=["super-admin"])
    headers = _headers(client, user)
    for method, path in CELERY_ROUTES:
        # Monitoring, history and control are all off in unit tests; that is not an
        # authorization denial.
        response = _call(client, method, path, headers=headers)
        assert response.status_code not in (401,), (method, path)
        assert response.get_json().get("error_code") not in ("permission_denied", "forbidden"), (method, path)


@pytest.mark.parametrize("role", ["editor", "tenant-admin"])
def test_permissions_check_matches_what_the_routes_enforce(client, db_session, role):
    """The designer shows the Celery page and its actions from POST /permissions-check.
    It must not report access via the group fallback that the routes turn off."""
    user = _provision(db_session, username=f"u-{role}", groups=[f"t1:{role}"])
    response = client.post(
        "/v1.0/permissions-check",
        json={"requests_to_check": {"/m8flow/celery/overview": ["GET"], "/m8flow/celery/control/revoke": ["POST"]}},
        headers=_headers(client, user),
    )
    assert response.status_code == 200
    results = response.get_json()["results"]
    assert results["/m8flow/celery/overview"]["GET"] is False
    assert results["/m8flow/celery/control/revoke"]["POST"] is False


def test_permissions_check_allows_super_admin(client, db_session):
    user = _provision(db_session, username="root", groups=["super-admin"])
    response = client.post(
        "/v1.0/permissions-check",
        json={"requests_to_check": {"/m8flow/celery/overview": ["GET"], "/m8flow/celery/control/revoke": ["POST"]}},
        headers=_headers(client, user),
    )
    results = response.get_json()["results"]
    assert results["/m8flow/celery/overview"]["GET"] is True
    assert results["/m8flow/celery/control/revoke"]["POST"] is True
