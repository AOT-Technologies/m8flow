from __future__ import annotations

import time
from pathlib import Path

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

BPMN = Path(__file__).resolve().parents[3] / "fixtures" / "invoice_approval_poc.bpmn"


def _login_user(client, db_session, *, username: str, groups: list[str], tenant_id: str):
    """Mirrors the shared route-test login helper (v1 'user' role -> task
    claim/complete command grants, needed for a real submit)."""
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


def _login_user_without_task_grant(client, db_session, *, username: str, tenant_id: str):
    """A viewer-only user with NO v1 'user' role: no task claim/complete grant
    and no editor/reviewer/':user' group -> denied on the /tasks surface."""
    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(
        db_session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=username,
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(
        db_session, user=user, group_identifiers=[f"{tenant_id}:viewer"], tenant_id=tenant_id
    )
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user, token


def _seed_instance(db_session, *, tenant_id: str, initiator_id: int, status: str = "user_input_required"):
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    now = int(time.time())
    instance = ProcessInstanceModel(
        m8f_tenant_id=tenant_id,
        process_model_identifier="finance/approval",
        process_model_display_name="Approval With Escalation",
        process_initiator_id=initiator_id,
        status=status,
        start_in_seconds=now - 100,
        end_in_seconds=None,
        last_milestone_bpmn_name="Manager Review",
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
    )
    db_session.add(instance)
    db_session.flush()
    return instance


def _seed_pending_task(
    db_session,
    *,
    tenant_id: str,
    process_instance_id: int,
    assignee_user_id: int,
    task_title: str = "Review Expense Claim",
    task_name: str = "review_expense_claim",
    created_at: int | None = None,
):
    from m8flow_bpmn_core.models.human_task import HumanTaskModel
    from m8flow_bpmn_core.models.human_task_user import HumanTaskUserModel

    now = created_at if created_at is not None else int(time.time())
    task = HumanTaskModel(
        m8f_tenant_id=tenant_id,
        process_instance_id=process_instance_id,
        task_name=task_name,
        task_title=task_title,
        task_type="User Task",
        task_status="READY",
        process_model_display_name="Approval With Escalation",
        bpmn_process_identifier="finance/approval-with-escalation",
        lane_name="Manager",
        completed=False,
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        HumanTaskUserModel(
            m8f_tenant_id=tenant_id,
            human_task_id=task.id,
            user_id=assignee_user_id,
        )
    )
    db_session.flush()
    return task


# --------------------------------------------------------------------------
# List
# --------------------------------------------------------------------------


def test_editor_lists_own_pending_tasks_with_projected_fields(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(db_session, tenant_id="t1", initiator_id=user.id)
    task = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=user.id,
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/task-review", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"] == {"page": 1, "per_page": 20, "total": 1}
    row = body["results"][0]
    assert row["id"] == task.id
    assert row["task_title"] == "Review Expense Claim"
    assert row["task_name"] == "review_expense_claim"
    assert row["process_model_display_name"] == "Approval With Escalation"
    assert row["process_instance_id"] == instance.id
    assert row["submitted_by"] == "editor"
    assert row["status"] == "READY"
    assert row["tenant_name"] == "t1"


def test_list_is_tenant_isolated(client, db_session):
    user1, token1 = _login_user(
        client, db_session, username="editor-t1", groups=["t1:editor"], tenant_id="t1"
    )
    user2, _token2 = _login_user(
        client, db_session, username="editor-t2", groups=["t2:editor"], tenant_id="t2"
    )
    inst1 = _seed_instance(db_session, tenant_id="t1", initiator_id=user1.id)
    inst2 = _seed_instance(db_session, tenant_id="t2", initiator_id=user2.id)
    mine = _seed_pending_task(
        db_session, tenant_id="t1", process_instance_id=inst1.id, assignee_user_id=user1.id
    )
    _seed_pending_task(
        db_session, tenant_id="t2", process_instance_id=inst2.id, assignee_user_id=user2.id
    )
    db_session.commit()

    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")
    response = client.get(
        "/v1.0/m8flow/task-review", headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    assert [r["id"] for r in response.get_json()["results"]] == [mine.id]


def test_list_only_own_assignments(client, db_session):
    editor, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    other, _ = _login_user(
        client, db_session, username="other-editor", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(db_session, tenant_id="t1", initiator_id=editor.id)
    mine = _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=editor.id,
        task_title="Mine",
    )
    _seed_pending_task(
        db_session,
        tenant_id="t1",
        process_instance_id=instance.id,
        assignee_user_id=other.id,
        task_title="Theirs",
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/task-review", headers={"Authorization": f"Bearer {token}"}
    )
    assert [r["id"] for r in response.get_json()["results"]] == [mine.id]


def test_list_pagination(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(db_session, tenant_id="t1", initiator_id=user.id)
    for i in range(3):
        _seed_pending_task(
            db_session,
            tenant_id="t1",
            process_instance_id=instance.id,
            assignee_user_id=user.id,
            task_title=f"Task {i}",
            created_at=1_700_000_000 + i,
        )
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    page1 = client.get("/v1.0/m8flow/task-review?per_page=2&page=1", headers=headers).get_json()
    assert page1["pagination"] == {"page": 1, "per_page": 2, "total": 3}
    assert len(page1["results"]) == 2

    page2 = client.get("/v1.0/m8flow/task-review?per_page=2&page=2", headers=headers).get_json()
    assert page2["pagination"] == {"page": 2, "per_page": 2, "total": 3}
    assert len(page2["results"]) == 1


def test_list_denied_caller_gets_empty_page(client, db_session):
    """A viewer without the task grant gets an empty page (200), not a 403 --
    same posture as list_process_instances."""
    user, token = _login_user_without_task_grant(
        client, db_session, username="viewer", tenant_id="t1"
    )
    instance = _seed_instance(db_session, tenant_id="t1", initiator_id=user.id)
    _seed_pending_task(
        db_session, tenant_id="t1", process_instance_id=instance.id, assignee_user_id=user.id
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/task-review", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "results": [],
        "pagination": {"page": 1, "per_page": 20, "total": 0},
    }


def test_super_admin_sees_all_tenants_and_tenant_id_override(client, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", name="Tenant Two", slug="t2")
    ensure_v1_role(db_session, tenant_id="t2", role_name="user", user_ids=(user.id,))
    inst1 = _seed_instance(db_session, tenant_id="t1", initiator_id=user.id)
    inst2 = _seed_instance(db_session, tenant_id="t2", initiator_id=user.id)
    t1_task = _seed_pending_task(
        db_session, tenant_id="t1", process_instance_id=inst1.id, assignee_user_id=user.id
    )
    t2_task = _seed_pending_task(
        db_session, tenant_id="t2", process_instance_id=inst2.id, assignee_user_id=user.id
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    all_tenants = client.get("/v1.0/m8flow/task-review", headers=headers)
    assert {r["id"] for r in all_tenants.get_json()["results"]} == {t1_task.id, t2_task.id}

    scoped = client.get("/v1.0/m8flow/task-review?tenantId=t2", headers=headers)
    scoped_rows = scoped.get_json()["results"]
    assert [r["id"] for r in scoped_rows] == [t2_task.id]
    assert scoped_rows[0]["tenant_name"] == "Tenant Two"


# --------------------------------------------------------------------------
# Detail
# --------------------------------------------------------------------------


def test_detail_composite_shape(client, db_session):
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    instance = _seed_instance(db_session, tenant_id="t1", initiator_id=user.id)
    task = _seed_pending_task(
        db_session, tenant_id="t1", process_instance_id=instance.id, assignee_user_id=user.id
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/task-review/{task.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert set(body.keys()) == {"task", "form", "outcomes", "approval_chain", "activity", "instance"}

    assert body["task"]["id"] == task.id
    assert body["task"]["task_title"] == "Review Expense Claim"
    assert body["task"]["task_type"] == "User Task"
    assert body["task"]["status"] == "READY"
    assert body["task"]["completed"] is False
    assert body["task"]["bpmn_process_identifier"] == "finance/approval-with-escalation"
    assert body["task"]["submitted_by"] == "editor"

    assert body["form"] == {"schema": {"type": "object", "properties": {}}, "ui_schema": None, "values": {}}
    assert body["outcomes"] == []  # linear task -> no gateway outcomes
    assert body["activity"] == []

    # approval_chain includes the current human task.
    assert any(entry["is_current"] for entry in body["approval_chain"])

    assert body["instance"]["id"] == instance.id
    assert body["instance"]["status"] == "user_input_required"
    assert body["instance"]["last_milestone_bpmn_name"] == "Manager Review"
    assert body["instance"]["detail_path"] == f"/process-instances/{instance.id}"


def test_detail_missing_is_404(client, db_session):
    _user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/task-review/999999", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_detail_other_tenant_is_404(client, db_session):
    user2, _token2 = _login_user(
        client, db_session, username="editor-t2", groups=["t2:editor"], tenant_id="t2"
    )
    other_instance = _seed_instance(db_session, tenant_id="t2", initiator_id=user2.id)
    other_task = _seed_pending_task(
        db_session,
        tenant_id="t2",
        process_instance_id=other_instance.id,
        assignee_user_id=user2.id,
    )
    db_session.commit()

    _user1, token1 = _login_user(
        client, db_session, username="editor-t1", groups=["t1:editor"], tenant_id="t1"
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")
    response = client.get(
        f"/v1.0/m8flow/task-review/{other_task.id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Submit
# --------------------------------------------------------------------------


def _start_real_instance(db_session, *, tenant_id, user):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    from m8flow_backend import catalog, workflow

    # Importing a definition (catalog.save) needs process_definition.import,
    # which the v1 'admin' role grants (the 'user' role does not).
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="admin", user_ids=(user.id,))
    xml = BPMN.read_text(encoding="utf-8")
    catalog.save(
        db_session, path="invoices/approval", xml=xml, tenant_id=tenant_id, user_id=user.id
    )
    instance = workflow.start(
        db_session,
        tenant_id=tenant_id,
        user_id=user.id,
        process_model_identifier="invoices/approval",
    )
    pending = workflow.list_pending_tasks(db_session, tenant_id=tenant_id, user_id=user.id)
    return instance, pending[0]


def test_submit_happy_path_advances_instance(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    instance, task = _start_real_instance(db_session, tenant_id="t1", user=user)
    db_session.commit()

    response = client.post(
        f"/v1.0/m8flow/task-review/{task.id}/submit",
        json={"comment": "Looks good, within policy."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["process_instance_id"] == instance.id
    assert body["process_status"] == "complete"
    assert body["process_complete"] is True
    assert "Task completed" in body["message"]


def test_submit_forwards_all_form_fields(client, db_session, tmp_path, monkeypatch):
    """The whole submitted form (its schema fields + the reserved `outcome`) is
    forwarded as task_payload, not just outcome/comment; null values dropped."""
    from sqlalchemy import select

    from m8flow_bpmn_core.models.process_instance_metadata import ProcessInstanceMetadataModel

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    instance, task = _start_real_instance(db_session, tenant_id="t1", user=user)
    db_session.commit()

    response = client.post(
        f"/v1.0/m8flow/task-review/{task.id}/submit",
        json={"reason": "Client renewal trip", "amount": 842.5, "outcome": "approve", "unset": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    rows = db_session.scalars(
        select(ProcessInstanceMetadataModel).where(
            ProcessInstanceMetadataModel.process_instance_id == instance.id,
            ProcessInstanceMetadataModel.m8f_tenant_id == "t1",
        )
    ).all()
    keys = {row.key for row in rows}
    assert {"reason", "amount", "outcome"}.issubset(keys)
    assert "unset" not in keys  # null values are dropped


def test_submit_already_completed_is_conflict(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    _instance, task = _start_real_instance(db_session, tenant_id="t1", user=user)
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(f"/v1.0/m8flow/task-review/{task.id}/submit", json={}, headers=headers)
    assert first.status_code == 200

    second = client.post(f"/v1.0/m8flow/task-review/{task.id}/submit", json={}, headers=headers)
    assert second.status_code == 409


def test_submit_on_suspended_instance_is_conflict(client, db_session, tmp_path, monkeypatch):
    from m8flow_backend import workflow

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    instance, task = _start_real_instance(db_session, tenant_id="t1", user=user)
    db_session.commit()
    workflow.suspend_instance(
        db_session, tenant_id="t1", process_instance_id=instance.id, user_id=user.id
    )
    db_session.commit()

    response = client.post(
        f"/v1.0/m8flow/task-review/{task.id}/submit",
        json={"comment": "should not land"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    db_session.refresh(instance)
    assert instance.status == "suspended"
    db_session.refresh(task)
    assert task.completed is False


def test_submit_forbidden_is_403(client, db_session):
    _user, token = _login_user_without_task_grant(
        client, db_session, username="viewer", tenant_id="t1"
    )
    db_session.commit()

    response = client.post(
        "/v1.0/m8flow/task-review/123/submit",
        json={"comment": "no"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_submit_editor_passes_route_gate(client, db_session):
    """A plain `editor` (manage-tasks grant, no admin) must clear the route gate
    -- the real 403 regression. Gate authorizes on `/tasks/{id}` (not the
    stricter `/tasks/{id}/complete`), so a missing task yields 404, not 403.
    """
    _user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    db_session.commit()
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")

    response = client.post(
        "/v1.0/m8flow/task-review/999999/submit",
        json={"reason": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404  # past the gate (403 would mean gate blocked editor)


HTTP_THEN_APPROVAL_BPMN = Path(__file__).resolve().parents[3] / "fixtures" / "approval_then_http.bpmn"


def _start_http_followup_instance(db_session, *, tenant_id, user, xml: str | None = None):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    from m8flow_backend import catalog, workflow

    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="admin", user_ids=(user.id,))
    catalog.save(
        db_session,
        path="http/approval",
        xml=(xml or HTTP_THEN_APPROVAL_BPMN.read_text(encoding="utf-8")),
        tenant_id=tenant_id,
        user_id=user.id,
    )
    instance = workflow.start(
        db_session,
        tenant_id=tenant_id,
        user_id=user.id,
        process_model_identifier="http/approval",
    )
    pending = workflow.list_pending_tasks(db_session, tenant_id=tenant_id, user_id=user.id)
    return instance, pending[0]


def test_submit_unquoted_http_url_runs_the_connector(
    client, db_session, tmp_path, monkeypatch
):
    """The properties panel stores URL params unquoted. Submit must still POST."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    posts: list[tuple[str, dict]] = []

    class _Stub(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps(
                [
                    {
                        "id": "http/PostRequestV2",
                        "parameters": [
                            {"id": "url", "type": "str", "required": True},
                            {"id": "data", "type": "any", "required": False},
                        ],
                    }
                ]
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            posts.append((self.path, json.loads(raw.decode("utf-8")) if raw else {}))
            body = json.dumps(
                {
                    "command_response": {
                        "body": {"ok": True},
                        "mimetype": "application/json",
                        "http_status": 200,
                    },
                    "error": None,
                    "command_response_version": 2,
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    monkeypatch.setenv("M8FLOW_BACKEND_CONNECTOR_PROXY_URL", f"http://{host}:{port}")
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_CONNECTOR_PROXY_URL", raising=False)
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    try:
        user, token = _login_user(
            client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
        )
        instance, task = _start_http_followup_instance(
            db_session, tenant_id="t1", user=user
        )
        db_session.commit()

        response = client.post(
            f"/v1.0/m8flow/task-review/{task.id}/submit",
            json={"decision": "approved"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.get_json()
        assert posts, "connector proxy never received the PostRequestV2"
        path, payload = posts[-1]
        assert path.rstrip("/").endswith("PostRequestV2")
        assert payload["url"] == "https://example.test/hook"
        db_session.refresh(task)
        assert task.completed is True
        db_session.refresh(instance)
        assert instance.status == "complete"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_submit_connector_failure_does_not_complete_the_human_task(
    client, db_session, tmp_path, monkeypatch
):
    """A 500 from the next Service Task must not leave the approval marked done."""
    broken = HTTP_THEN_APPROVAL_BPMN.read_text(encoding="utf-8").replace(
        "http/PostRequestV2", "http/NotARealCommand"
    )
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    _instance, task = _start_http_followup_instance(
        db_session, tenant_id="t1", user=user, xml=broken
    )
    db_session.commit()

    response = client.post(
        f"/v1.0/m8flow/task-review/{task.id}/submit",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 500
    db_session.refresh(task)
    assert task.completed is False


# --------------------------------------------------------------------------
# AGENTS.md shared-realm regression (non-admin user, incl. multi-org)
# --------------------------------------------------------------------------


def test_reviewer_regression_onboarding_tasks_and_task_review_multi_org(client, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    user, token = _login_user(
        client, db_session, username="reviewer", groups=["org-a:reviewer"], tenant_id="org-a"
    )
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200
    assert client.get("/v1.0/m8flow/task-review", headers=headers).status_code == 200

    # Reviewer joins a second organization; must still access all three.
    tenant_b = ensure_tenant(db_session, tenant_id="org-b", slug="org-b")
    ensure_membership(db_session, user, tenant_b)
    sync_groups(db_session, user=user, group_identifiers=["org-b:reviewer"], tenant_id="org-b")
    ensure_v1_role(db_session, tenant_id="org-b", role_name="user", user_ids=(user.id,))
    db_session.commit()
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "org-b")

    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200
    review = client.get("/v1.0/m8flow/task-review", headers=headers)
    assert review.status_code == 200
    assert review.get_json()["pagination"]["total"] == 0
