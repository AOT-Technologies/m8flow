from __future__ import annotations

from types import SimpleNamespace

from flask import g

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.auth.tenant_context import (
    SELECTED_TENANT_COOKIE_NAME,
    TENANT_SELECTION_HEADER_NAME,
    get_context_tenant_id,
    reset_context_tenant_id,
    set_context_tenant_id,
)
from m8flow_backend.auth.bind import apply_postgres_rls, resolve_request_tenant
from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, VerifiedClaims


class _FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeCursor:
    def __init__(self, owner: "_FakeConnection") -> None:
        self.owner = owner

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.owner.calls.append((sql, params))

    def close(self) -> None:
        self.owner.close_calls += 1


class _FakeConnection:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = _FakeDialect(dialect_name)
        self.calls: list[tuple[str, tuple | None]] = []
        self.connection = self
        self.close_calls = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def exec_driver_sql(self, sql: str, params: tuple | None = None) -> None:
        # PostgreSQL SET / SET LOCAL cannot take bind parameters. psycopg3
        # emits $1 and the server raises SyntaxError, aborting the request
        # transaction so every subsequent query 500s.
        if sql.strip().upper().startswith("SET ") and params:
            raise RuntimeError("postgres SET does not accept bind parameters")
        self.calls.append((sql, params))


def _login(client, db_session, *, username: str, groups: list[str], tenant_id: str):
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


def test_cookie_binds_tenant_on_protected_route(client, db_session):
    _user, token = _login(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.get("/v1.0/onboarding", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.get_json()["tenant_id"] == "t1"
    # Home reads instructions.length on every non-empty onboarding response.
    assert response.get_json()["instructions"] == ""
    tasks = client.get("/v1.0/tasks", headers={"Authorization": f"Bearer {token}"})
    assert tasks.status_code == 200


def test_group_sync_reconciles_pending_tasks_for_active_tenant(app, db_session, monkeypatch):
    from m8flow_bpmn_core.models.user_group_assignment import UserGroupAssignmentModel
    from m8flow_bpmn_core.models.group import GroupModel
    from m8flow_bpmn_core.services.workflow_runtime import resolve_lane_assignment_id
    from m8flow_backend.auth import sync_groups_from_token

    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(
        db_session,
        username="submitter",
        service="https://example.test/realms/m8flow",
        service_id="submitter-1",
    )
    ensure_membership(db_session, user, tenant)
    db_session.flush()
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "m8flow_backend.identity.tenant_yaml_grants_present",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "m8flow_backend.workflow.reconcile_pending_tasks_for_user",
        lambda _session, *, tenant_id, user_id: calls.append((tenant_id, user_id)) or [],
    )
    claims = VerifiedClaims(
        subject="submitter-1",
        issuer="https://example.test/realms/m8flow",
        username="submitter",
        memberships=[
            Membership(
                tenant_ref=TenantRef(id="t1"),
                roles=["submitter"],
                groups=["Submitters"],
            )
        ],
    )
    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")

    assert calls == [(tenant.id, user.id)]
    lane_group_id = resolve_lane_assignment_id("Submitters", tenant.id)
    lane_group = db_session.get(GroupModel, lane_group_id)
    assert lane_group is not None
    assert lane_group.name == "t1:Submitters"
    assert lane_group.identifier == "t1:Submitters"
    assert (
        db_session.query(UserGroupAssignmentModel)
        .filter_by(user_id=user.id, group_id=lane_group_id)
        .count()
        == 1
    )


def test_group_sync_keeps_authentication_alive_when_reconciliation_fails(
    app, db_session, monkeypatch, caplog
):
    from m8flow_backend.auth import sync_groups_from_token

    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(
        db_session,
        username="submitter",
        service="https://example.test/realms/m8flow",
        service_id="submitter-1",
    )
    ensure_membership(db_session, user, tenant)
    db_session.flush()
    monkeypatch.setattr(
        "m8flow_backend.identity.tenant_yaml_grants_present",
        lambda *_args, **_kwargs: True,
    )

    def fail_reconciliation(*_args, **_kwargs):
        raise RuntimeError("temporary reconciliation failure")

    monkeypatch.setattr(
        "m8flow_backend.workflow.reconcile_pending_tasks_for_user",
        fail_reconciliation,
    )
    claims = VerifiedClaims(
        subject="submitter-1",
        issuer="https://example.test/realms/m8flow",
        username="submitter",
        memberships=[
            Membership(
                tenant_ref=TenantRef(id="t1"),
                roles=["submitter"],
                groups=["Submitters"],
            )
        ],
    )

    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")

    assert user.id is not None
    assert "Pending-task reconciliation failed" in caplog.text


def test_group_sync_assigns_existing_lane_task_without_claiming_it(app, db_session, monkeypatch):
    from m8flow_bpmn_core.models.group import GroupModel
    from m8flow_bpmn_core.models.human_task import HumanTaskModel
    from m8flow_bpmn_core.models.human_task_user import HumanTaskUserModel
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel, ProcessInstanceStatus
    from m8flow_bpmn_core.services.workflow_runtime import resolve_lane_assignment_id
    from m8flow_backend.auth import sync_groups_from_token

    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(
        db_session,
        username="submitter",
        service="https://example.test/realms/m8flow",
        service_id="submitter-1",
    )
    ensure_membership(db_session, user, tenant)
    lane_group_id = resolve_lane_assignment_id("Submitters", tenant.id)
    db_session.add(
            GroupModel(
                id=lane_group_id,
                name=f"{tenant.id}:Submitters",
                identifier=f"{tenant.id}:Submitters",
                source_is_open_id=False,
        )
    )
    instance = ProcessInstanceModel(
        m8f_tenant_id=tenant.id,
        process_model_identifier="approval/process",
        process_model_display_name="Approval process",
        process_initiator_id=user.id,
        status=ProcessInstanceStatus.user_input_required.value,
    )
    db_session.add(instance)
    db_session.flush()
    task = HumanTaskModel(
        m8f_tenant_id=tenant.id,
        process_instance_id=instance.id,
        lane_assignment_id=lane_group_id,
        task_name="submit",
        task_type="UserTask",
        task_status="READY",
        process_model_display_name=instance.process_model_display_name,
        bpmn_process_identifier=instance.process_model_identifier,
        lane_name="Submitters",
        completed=False,
        actual_owner_id=None,
    )
    db_session.add(task)
    db_session.flush()
    monkeypatch.setattr(
        "m8flow_backend.identity.tenant_yaml_grants_present",
        lambda *_args, **_kwargs: True,
    )
    claims = VerifiedClaims(
        subject="submitter-1",
        issuer="https://example.test/realms/m8flow",
        username="submitter",
        memberships=[
            Membership(
                tenant_ref=TenantRef(id="t1"),
                roles=["submitter"],
                groups=["Submitters"],
            )
        ],
    )

    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")

    assignments = db_session.query(HumanTaskUserModel).filter_by(human_task_id=task.id).all()
    assert [(assignment.user_id, assignment.added_by) for assignment in assignments] == [
        (user.id, "lane_assignment")
    ]
    assert task.actual_owner_id is None


def test_fail_closed_without_tenant_on_protected_route(client, db_session):
    _user, token = _login(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)
    response = client.get("/v1.0/onboarding", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_required"


def test_exempt_path_does_not_require_tenant(client):
    response = client.get("/v1.0/status")
    assert response.status_code == 200


def test_header_allowed_when_user_belongs(client, db_session):
    _user, token = _login(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)
    response = client.get(
        "/v1.0/onboarding",
        headers={
            "Authorization": f"Bearer {token}",
            TENANT_SELECTION_HEADER_NAME: "t1",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["tenant_id"] == "t1"


def test_header_rejected_when_user_does_not_belong(client, db_session):
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()
    _user, token = _login(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)
    response = client.get(
        "/v1.0/onboarding",
        headers={
            "Authorization": f"Bearer {token}",
            TENANT_SELECTION_HEADER_NAME: "t2",
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_override_forbidden"


def test_cookie_wins_over_jwt_claim_for_multi_org_membership(app, db_session):
    ensure_tenant(db_session, tenant_id="org-a", slug="org-a")
    ensure_tenant(db_session, tenant_id="org-b", slug="org-b")
    db_session.commit()
    user = SimpleNamespace(
        groups=[SimpleNamespace(identifier="org-b:reviewer")], service_id=None, username=None
    )
    # VerifiedClaims is the contract resolve_request_tenant reads (auth-
    # provider-seam wayfinder map, ticket 10) -- active_tenant_ref carries
    # the explicit m8flow_tenant_id claim (org-a) and memberships carries
    # every organization (org-a, org-b), mirroring the raw payload this test
    # used to poke g.decoded_token with directly.
    claims = VerifiedClaims(
        subject="user-1",
        issuer="https://example.test/realms/m8flow",
        active_tenant_ref=TenantRef(id="org-a"),
        memberships=[
            Membership(tenant_ref=TenantRef(id="org-a", alias="org-a")),
            Membership(tenant_ref=TenantRef(id="org-b", alias="org-b")),
        ],
    )
    with app.test_request_context(
        "/v1.0/onboarding",
        headers={"Cookie": f"{SELECTED_TENANT_COOKIE_NAME}=org-b"},
    ):
        g.user = user
        g.verified_claims = claims
        g.db_session = db_session
        resolve_request_tenant()
        assert g.m8flow_tenant_id == "org-b"


def test_super_admin_without_cookie_stays_exempt(client, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(
        db_session,
        username="root",
        service="https://example.test/realms/master",
        service_id="root",
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=["super-admin"], tenant_id="t1")
    ensure_v1_role(db_session, tenant_id="t1", role_name="user", user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    response = client.get("/v1.0/onboarding", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_super_admin_tenant_id_query_binds_override(client, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    user = ensure_user(
        db_session,
        username="root",
        service="https://example.test/realms/master",
        service_id="root",
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=["super-admin"], tenant_id="t1")
    ensure_v1_role(db_session, tenant_id="t1", role_name="user", user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    response = client.get(
        "/v1.0/onboarding",
        query_string={"tenantId": "t2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json()["tenant_id"] == "t2"


def test_postgres_sets_current_tenant_from_request(app):
    connection = _FakeConnection("postgresql")
    with app.test_request_context("/v1.0/tasks"):
        g.m8flow_tenant_id = "tenant-a"
        apply_postgres_rls(connection)
    assert connection.calls == [
        ("SELECT set_config(%s, %s, true)", ("app.current_tenant", "tenant-a")),
    ]


def test_postgres_sets_current_tenant_from_contextvar():
    connection = _FakeConnection("postgresql")
    token = set_context_tenant_id("tenant-b")
    try:
        apply_postgres_rls(connection)
    finally:
        reset_context_tenant_id(token)
    assert connection.calls == [
        ("SELECT set_config(%s, %s, true)", ("app.current_tenant", "tenant-b")),
    ]


def test_postgres_missing_tenant_does_nothing():
    connection = _FakeConnection("postgresql")
    apply_postgres_rls(connection)
    assert connection.calls == []
    assert connection.close_calls == 0


def test_non_postgres_does_nothing():
    connection = _FakeConnection("sqlite")
    apply_postgres_rls(connection)
    assert connection.calls == []


def test_postgres_super_admin_without_tenant_sets_bypass_only(app, monkeypatch):
    connection = _FakeConnection("postgresql")
    monkeypatch.setattr(
        "m8flow_backend.auth.bind.is_super_admin_request",
        lambda: True,
    )
    with app.test_request_context("/v1.0/onboarding"):
        g._m8flow_tenant_context_exempt_request = True
        apply_postgres_rls(connection)
    assert connection.calls == [
        ("SELECT set_config(%s, %s, true)", ("app.bypass_rls", "on")),
    ]


def test_postgres_super_admin_with_tenant_sets_bypass_and_current(app, monkeypatch):
    connection = _FakeConnection("postgresql")
    monkeypatch.setattr(
        "m8flow_backend.auth.bind.is_super_admin_request",
        lambda: True,
    )
    with app.test_request_context("/v1.0/onboarding"):
        g.m8flow_tenant_id = "t2"
        apply_postgres_rls(connection)
    assert connection.calls == [
        ("SELECT set_config(%s, %s, true)", ("app.bypass_rls", "on")),
        ("SELECT set_config(%s, %s, true)", ("app.current_tenant", "t2")),
    ]


def test_postgres_exempt_non_super_admin_skips_session_flags(app):
    connection = _FakeConnection("postgresql")
    with app.test_request_context("/v1.0/status"):
        g._m8flow_tenant_context_exempt_request = True
        apply_postgres_rls(connection)
    assert connection.calls == []


def test_resolve_request_tenant_direct_cookie_bind(app, db_session):
    ensure_tenant(db_session, tenant_id="t1", slug="t1")
    db_session.commit()
    user = SimpleNamespace(groups=[SimpleNamespace(identifier="t1:editor")])
    with app.test_request_context(
        "/v1.0/tasks",
        headers={"Cookie": f"{SELECTED_TENANT_COOKIE_NAME}=t1"},
    ):
        g.user = user
        g.db_session = db_session
        resolve_request_tenant()
        assert g.m8flow_tenant_id == "t1"
        assert get_context_tenant_id() == "t1"


def test_cookie_fallback_rejected_when_user_does_not_belong(client, db_session):
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()
    _user, token = _login(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t2")
    response = client.get("/v1.0/onboarding", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_override_forbidden"


def test_cookie_fallback_rejected_in_direct_resolve(app, db_session):
    ensure_tenant(db_session, tenant_id="t1", slug="t1")
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()
    user = SimpleNamespace(groups=[SimpleNamespace(identifier="t1:editor")])
    with app.test_request_context(
        "/v1.0/tasks",
        headers={"Cookie": f"{SELECTED_TENANT_COOKIE_NAME}=t2"},
    ):
        g.user = user
        g.db_session = db_session
        try:
            resolve_request_tenant()
            raised = None
        except Exception as exc:  # noqa: BLE001 -- assert ApiError below
            raised = exc
    from m8flow_backend.errors import ApiError

    assert isinstance(raised, ApiError)
    assert raised.error_code == "tenant_override_forbidden"
