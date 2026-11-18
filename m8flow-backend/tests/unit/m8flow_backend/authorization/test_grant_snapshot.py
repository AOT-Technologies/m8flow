"""M8F-703: a request loads the caller's grants once, however many checks it runs.

Batch endpoints (permissions-check, capabilities, home-stats) used to reload every
permission assignment for every (uri, method) they checked. The snapshot must not
change any decision: tenant scoping, deny rows and grants written earlier in the
same request all still apply.
"""

from __future__ import annotations

from flask import g
from sqlalchemy import event, select

from m8flow_backend import identity
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.authorization import allow_uri
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_core.models.group import GroupModel
from m8flow_core.models.principal import PrincipalModel

_SERVICE = "https://example.test/realms/m8flow"

# A spread of what SessionProvider.tsx sends at bootstrap: list, item and
# lifecycle paths, no-fallback prefixes, and every verb.
_THIRTY_TARGETS = {
    "/process-models": ["GET", "POST", "PUT"],
    "/process-models/capability-check": ["DELETE"],
    "/process-models/{id}/copy": ["POST"],
    "/process-models/{id}/files/{file}": ["PUT", "DELETE"],
    "/process-groups": ["POST"],
    "/process-groups/{id}": ["PUT", "DELETE"],
    "/process-instances": ["GET", "POST"],
    "/process-instances/for-me": ["GET"],
    "/process-instances/{id}/suspend": ["POST"],
    "/process-instances/{id}/resume": ["POST"],
    "/process-instances/{id}/terminate": ["POST"],
    "/process-instances/{id}": ["DELETE"],
    "/secrets": ["GET", "POST"],
    "/secrets/{key}": ["PUT", "DELETE"],
    "/m8flow/templates": ["POST"],
    "/m8flow/templates/{id}": ["PUT", "DELETE"],
    "/m8flow/connector-profiles": ["POST"],
    "/m8flow/named-values": ["GET", "POST"],
    "/m8flow/nats-tokens": ["GET", "POST"],
    "/m8flow/celery/overview": ["GET"],
}


def _user_with_roles(db_session, username: str, roles_by_tenant: dict[str, list[str]]):
    user = ensure_user(db_session, username=username, service=_SERVICE, service_id=username)
    for tenant_id, roles in roles_by_tenant.items():
        tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
        ensure_membership(db_session, user, tenant)
        sync_groups(
            db_session,
            user=user,
            group_identifiers=[f"{tenant_id}:{role}" for role in roles],
            tenant_id=tenant_id,
        )
        identity.import_yaml(db_session, tenant_id=tenant_id)
    db_session.commit()
    return user


def _headers(client, user, tenant_id: str) -> dict[str, str]:
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return {"Authorization": f"Bearer {encode_auth_token(user=user)}"}


def _selects(db_session, call) -> tuple[object, list[str]]:
    """Run `call` and return its result plus every SELECT it issued (lowercased)."""
    seen: list[str] = []
    engine = db_session.get_bind()

    def _before(_conn, _cursor, statement, _parameters, _context, _executemany):
        seen.append(statement.lower())

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = call()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, [sql for sql in seen if sql.lstrip().startswith("select")]


def _count_assignment_loads(db_session, call) -> tuple[object, int]:
    """Run `call` and count the SELECTs that load permission assignments."""
    result, selects = _selects(db_session, call)
    return result, sum("from permission_assignment" in sql for sql in selects)


def _group_principal(db_session, identifier: str) -> PrincipalModel:
    group = db_session.scalars(select(GroupModel).where(GroupModel.identifier == identifier)).one()
    return db_session.scalars(select(PrincipalModel).where(PrincipalModel.group_id == group.id)).one()


def test_permissions_check_loads_grants_once_for_thirty_targets(client, db_session):
    user = _user_with_roles(db_session, "snapshot-editor", {"t1": ["editor"]})
    headers = _headers(client, user, "t1")

    response, loads = _count_assignment_loads(
        db_session,
        lambda: client.post(
            "/v1.0/permissions-check",
            headers=headers,
            json={"requests_to_check": _THIRTY_TARGETS},
        ),
    )

    assert response.status_code == 200
    assert sum(len(methods) for methods in _THIRTY_TARGETS.values()) == 30
    assert loads <= 1, f"permission assignments loaded {loads} times for one request"


def test_capabilities_loads_grants_once(client, db_session):
    user = _user_with_roles(db_session, "snapshot-caps", {"t1": ["editor"]})
    headers = _headers(client, user, "t1")

    response, loads = _count_assignment_loads(
        db_session, lambda: client.get("/v1.0/m8flow/capabilities", headers=headers)
    )

    assert response.status_code == 200
    assert loads <= 1, f"permission assignments loaded {loads} times for one request"


def test_snapshot_is_scoped_to_the_active_tenant(client, db_session):
    """A multi-org user's role in one organization never grants in another."""
    user = _user_with_roles(db_session, "snapshot-multi", {"t1": ["editor"], "t2": ["viewer"]})
    body = {"requests_to_check": {"/process-models": ["GET", "POST"], "/secrets": ["GET"]}}

    as_t1 = client.post("/v1.0/permissions-check", headers=_headers(client, user, "t1"), json=body)
    as_t2 = client.post("/v1.0/permissions-check", headers=_headers(client, user, "t2"), json=body)

    assert as_t1.get_json()["results"] == {
        "/process-models": {"GET": True, "POST": True},
        "/secrets": {"GET": False},
    }
    assert as_t2.get_json()["results"] == {
        "/process-models": {"GET": True, "POST": False},
        "/secrets": {"GET": True},
    }


def test_snapshot_sees_a_grant_written_earlier_in_the_request(app, db_session):
    user = _user_with_roles(db_session, "snapshot-late-grant", {"t1": ["editor"]})

    with app.test_request_context("/v1.0/permissions-check"):
        g.db_session = db_session
        g.m8flow_tenant_id = "t1"
        assert allow_uri(user, "GET", "/v1.0/secrets", session=db_session) is False

        identity.grant(
            db_session,
            principal=_group_principal(db_session, "t1:editor"),
            uri="/secrets",
            permission="read",
        )

        assert allow_uri(user, "GET", "/v1.0/secrets", session=db_session) is True


def test_snapshot_survives_a_commit_without_reloading_rows(app, db_session):
    """Commit expires ORM rows; the snapshot must not lazy-load them one by one."""
    user = _user_with_roles(db_session, "snapshot-commit", {"t1": ["editor"]})

    with app.test_request_context("/v1.0/permissions-check"):
        g.db_session = db_session
        g.m8flow_tenant_id = "t1"
        assert allow_uri(user, "GET", "/v1.0/process-models", session=db_session) is True
        db_session.commit()

        allowed, selects = _selects(
            db_session,
            lambda: allow_uri(user, "PUT", "/v1.0/process-models/x", session=db_session),
        )

    assert allowed is True
    assert [sql for sql in selects if "permission_" in sql] == []


def test_snapshot_still_applies_deny_rows(app, db_session):
    user = _user_with_roles(db_session, "snapshot-deny", {"t1": ["editor"]})
    identity.grant(
        db_session,
        principal=_group_principal(db_session, "t1:editor"),
        uri="/process-models",
        permission="read",
        grant_type="deny",
    )
    db_session.commit()

    with app.test_request_context("/v1.0/permissions-check"):
        g.db_session = db_session
        g.m8flow_tenant_id = "t1"
        first = allow_uri(user, "GET", "/v1.0/process-models", session=db_session, group_fallback=False)
        second = allow_uri(user, "GET", "/v1.0/process-models", session=db_session, group_fallback=False)

    assert (first, second) == (False, False)


def _get_onboarding_and_tasks(client, user, tenant_id: str) -> tuple[int, int]:
    headers = _headers(client, user, tenant_id)
    onboarding = client.get("/v1.0/onboarding", headers=headers)
    tasks = client.get("/v1.0/tasks", headers=headers)
    return onboarding.status_code, tasks.status_code


def test_editor_and_reviewer_still_reach_onboarding_and_tasks(client, db_session):
    """AGENTS.md: non-admin shared-realm users keep their protected-route access."""
    editor = _user_with_roles(db_session, "snapshot-route-editor", {"t1": ["editor"]})
    reviewer = _user_with_roles(db_session, "snapshot-route-reviewer", {"t1": ["reviewer"]})

    assert _get_onboarding_and_tasks(client, editor, "t1") == (200, 200)
    assert _get_onboarding_and_tasks(client, reviewer, "t1") == (200, 200)


def test_multi_org_editor_reaches_onboarding_and_tasks_in_each_org(client, db_session):
    """An editor who joins a second organization keeps access after selecting either."""
    editor = _user_with_roles(
        db_session, "snapshot-route-multi", {"t1": ["editor"], "t2": ["editor"]}
    )

    assert _get_onboarding_and_tasks(client, editor, "t1") == (200, 200)
    assert _get_onboarding_and_tasks(client, editor, "t2") == (200, 200)
    assert _get_onboarding_and_tasks(client, editor, "t1") == (200, 200)
