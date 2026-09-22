from __future__ import annotations

import json
import time
from pathlib import Path

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.routes.processes_controller import process_model_identifier_from_path_param
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

VALID_BPMN = Path(__file__).resolve().parents[3] / "fixtures" / "invoice_approval_poc.bpmn"


def test_path_param_unquotes_colon_and_double_encoding():
    assert process_model_identifier_from_path_param("finance:invoice-approval") == (
        "finance/invoice-approval"
    )
    assert process_model_identifier_from_path_param("finance%3Ainvoice-approval") == (
        "finance/invoice-approval"
    )
    assert process_model_identifier_from_path_param("finance%253Ainvoice-approval") == (
        "finance/invoice-approval"
    )


def _login_user(
    client, db_session, *, username: str, groups: list[str], tenant_id: str, v1_role: str = "user"
):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(
        db_session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=username,
    )
    ensure_membership(db_session, user, ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id))
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name=v1_role, user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user, token


def _seed_catalog(tmp_path, monkeypatch, *, tenant_id: str) -> None:
    root = tmp_path / "bpmn" / tenant_id
    model_dir = root / "finance" / "invoice-approval"
    model_dir.mkdir(parents=True)
    (root / "finance" / "process_group.json").write_text(
        json.dumps({"display_name": "Finance", "description": "Finance flows"}),
        encoding="utf-8",
    )
    (model_dir / "invoice-approval.bpmn").write_text(
        '<?xml version="1.0"?><definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"/>',
        encoding="utf-8",
    )
    (model_dir / "invoice-form-schema.json").write_text("{}", encoding="utf-8")
    (model_dir / "process_model.json").write_text(
        json.dumps(
            {
                "display_name": "Invoice Approval",
                "description": "Two-step",
                "primary_file_name": "invoice-approval.bpmn",
                # Published so the start-path tests exercise starting, not the
                # publish gate. `onboarding/new-hire` below deliberately has no
                # status, covering the draft default.
                "status": "published",
            }
        ),
        encoding="utf-8",
    )
    other = root / "onboarding" / "new-hire"
    other.mkdir(parents=True)
    (root / "onboarding" / "process_group.json").write_text(
        json.dumps({"display_name": "Onboarding"}),
        encoding="utf-8",
    )
    (other / "process_model.json").write_text(
        json.dumps({"display_name": "New Hire", "status": "draft"}),
        encoding="utf-8",
    )
    (other / "new-hire.bpmn").write_text(
        '<?xml version="1.0"?><definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"/>',
        encoding="utf-8",
    )
    empty = root / "archived"
    empty.mkdir(parents=True)
    (empty / "process_group.json").write_text(
        json.dumps({"display_name": "Archived", "description": "No models yet"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))


def _seed_instance(
    db_session,
    *,
    tenant_id: str,
    initiator_id: int,
    process_model_identifier: str,
    start: int | None,
    status: str = "complete",
):
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    now = int(time.time())
    terminal = status in {"complete", "error", "terminated"}
    instance = ProcessInstanceModel(
        m8f_tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        process_model_display_name=process_model_identifier.split("/")[-1],
        process_initiator_id=initiator_id,
        status=status,
        start_in_seconds=start,
        end_in_seconds=start + 60 if start is not None and terminal else None,
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
    )
    db_session.add(instance)
    db_session.flush()
    return instance


def test_editor_lists_models_with_run_stats(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now - 60,
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now - 40 * 24 * 60 * 60,  # outside 30d window
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 2
    by_id = {row["id"]: row for row in body}
    invoice = by_id["finance/invoice-approval"]
    assert invoice["display_name"] == "Invoice Approval"
    assert invoice["group_id"] == "finance"
    assert invoice["group_display_name"] == "Finance"
    assert invoice["last_run_in_seconds"] == now - 60
    assert invoice["runs_30d"] == 1
    assert invoice["status"] == "published"
    hire = by_id["onboarding/new-hire"]
    assert hire["display_name"] == "New Hire"
    assert hire["last_run_in_seconds"] is None
    assert hire["runs_30d"] == 0
    assert hire["status"] == "draft"


def test_process_models_can_filter_by_process_initiator(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    owner_a, token = _login_user(
        client, db_session, username="owner-a", groups=["t1:editor"], tenant_id="t1"
    )
    owner_b = ensure_user(
        db_session,
        username="owner-b",
        service="https://example.test/realms/m8flow",
        service_id="owner-b",
    )
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=owner_a.id,
        process_model_identifier="finance/invoice-approval",
        start=now,
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=owner_b.id,
        process_model_identifier="onboarding/new-hire",
        start=now,
    )
    db_session.commit()

    response = client.get(
        f"/v1.0/m8flow/process-models?started_by_id={owner_b.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.get_json()] == ["onboarding/new-hire"]


def test_process_model_owner_filter_uses_stable_user_id_for_duplicate_usernames(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    owner_t1 = ensure_user(
        db_session,
        username="same-name",
        service="https://issuer-a.example.test",
        service_id="subject-a",
    )
    owner_t2 = ensure_user(
        db_session,
        username="same-name",
        service="https://issuer-b.example.test",
        service_id="subject-b",
    )
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=owner_t1.id,
        process_model_identifier="finance/invoice-approval",
        start=now,
    )
    _seed_instance(
        db_session,
        tenant_id="t2",
        initiator_id=owner_t2.id,
        process_model_identifier="finance/invoice-approval",
        start=now,
    )
    db_session.commit()
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)

    response = client.get(
        f"/v1.0/m8flow/process-models?started_by_id={owner_t1.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    rows = response.get_json()
    assert [(row["tenant_id"], row["id"]) for row in rows] == [
        ("t1", "finance/invoice-approval")
    ]


def test_catalog_list_does_not_include_another_tenants_files(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    other = tmp_path / "bpmn" / "t2" / "secret" / "payroll"
    other.mkdir(parents=True)
    (other / "payroll.bpmn").write_text(
        '<?xml version="1.0"?><definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"/>',
        encoding="utf-8",
    )

    _user, token = _login_user(
        client, db_session, username="editor-files", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.get(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    ids = {row["id"] for row in response.get_json()}
    assert "secret/payroll" not in ids
    assert "finance/invoice-approval" in ids


def test_group_filter_and_unknown_group(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor2", groups=["t1:editor"], tenant_id="t1"
    )

    filtered = client.get(
        "/v1.0/m8flow/process-models?group=finance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert filtered.status_code == 200
    rows = filtered.get_json()
    assert [row["id"] for row in rows] == ["finance/invoice-approval"]

    missing = client.get(
        "/v1.0/m8flow/process-models?group=does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 200
    assert missing.get_json() == []


def test_reviewer_gets_empty_list(client, db_session, tmp_path, monkeypatch):
    """reviewer lacks /process-models list grant (and editor fallback); [] not 403."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="reviewer", groups=["t1:reviewer"], tenant_id="t1"
    )

    response = client.get(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json() == []


def test_super_admin_lists_models_across_tenants(client, db_session, tmp_path, monkeypatch):
    """All Tenants (no cookie, no tenantId) fans out over the registered
    tenants' catalog directories. Model identifiers are catalog paths and DO
    collide across tenants, so every row carries its own tenant_id.
    """
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="super-admin", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", name="Tenant Two", slug="t2")
    db_session.commit()
    # Drop the cookie _login_user set so All Tenants has no concrete tenant.
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)

    merged = client.get(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert merged.status_code == 200
    rows = merged.get_json()
    assert {row["tenant_id"] for row in rows} == {"t1", "t2"}
    # The same identifier exists in both tenants and stays two distinct rows.
    collided = [r for r in rows if r["id"] == "finance/invoice-approval"]
    assert {r["tenant_id"] for r in collided} == {"t1", "t2"}

    ok = client.get(
        "/v1.0/m8flow/process-models?tenantId=t1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200
    assert len(ok.get_json()) == 2


def test_thin_v1_process_models_unchanged(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor3", groups=["t1:editor"], tenant_id="t1"
    )

    response = client.get(
        "/v1.0/process-models",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json() == [
        "finance/invoice-approval",
        "onboarding/new-hire",
    ]


def test_editor_lists_groups_with_empty_group_and_last_run(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="editor-groups", groups=["t1:editor"], tenant_id="t1"
    )
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now - 120,
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-groups",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    by_id = {row["id"]: row for row in body}
    assert set(by_id) == {"archived", "finance", "onboarding"}
    assert by_id["finance"]["display_name"] == "Finance"
    assert by_id["finance"]["description"] == "Finance flows"
    assert by_id["finance"]["model_count"] == 1
    assert by_id["finance"]["last_run_in_seconds"] == now - 120
    assert by_id["onboarding"]["model_count"] == 1
    assert by_id["onboarding"]["last_run_in_seconds"] is None
    assert by_id["onboarding"]["description"] == ""
    assert by_id["archived"]["display_name"] == "Archived"
    assert by_id["archived"]["model_count"] == 0
    assert by_id["archived"]["last_run_in_seconds"] is None


def test_reviewer_gets_empty_groups_list(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="reviewer-groups", groups=["t1:reviewer"], tenant_id="t1"
    )

    response = client.get(
        "/v1.0/m8flow/process-groups",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json() == []


def test_super_admin_catalog_write_still_requires_concrete_tenant(
    client, db_session, tmp_path, monkeypatch
):
    """Reads relax under All Tenants; catalog writes must not -- a create has
    to land in exactly one tenant (M8F-479)."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="super-admin-write", groups=["super-admin"], tenant_id="t1"
    )
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)

    response = client.post(
        "/v1.0/m8flow/process-groups",
        json={"id": "newgroup", "display_name": "New Group"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_required"


def test_super_admin_lists_groups_across_tenants(client, db_session, tmp_path, monkeypatch):
    """Groups fan out the same way as models under All Tenants."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="super-admin-groups", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", name="Tenant Two", slug="t2")
    db_session.commit()
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)

    merged = client.get(
        "/v1.0/m8flow/process-groups",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert merged.status_code == 200
    assert {row["tenant_id"] for row in merged.get_json()} == {"t1", "t2"}

    ok = client.get(
        "/v1.0/m8flow/process-groups?tenantId=t1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200
    assert len(ok.get_json()) == 3


def test_editor_gets_process_model_detail(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="editor-detail", groups=["t1:editor"], tenant_id="t1"
    )
    now = int(time.time())
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now - 90,
        status="complete",
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=now - 30,
        status="running",
    )
    db_session.commit()

    response = client.get(
        "/v1.0/m8flow/process-models/finance:invoice-approval",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["id"] == "finance/invoice-approval"
    assert body["display_name"] == "Invoice Approval"
    assert body["description"] == "Two-step"
    assert body["group_id"] == "finance"
    assert body["group_display_name"] == "Finance"
    assert body["last_run_in_seconds"] == now - 30
    assert body["running_now"] == 1
    assert body["runs_30d"] == 2
    assert len(body["recent_instances"]) == 2
    assert body["recent_instances"][0]["status"] == "running"
    assert body["recent_instances"][0]["started_by"] == "editor-detail"
    assert body["recent_instances"][0]["duration_seconds"] is None
    assert body["recent_instances"][1]["duration_seconds"] == 60
    names = {f["name"]: f for f in body["files"]}
    assert "invoice-approval.bpmn" in names
    assert names["invoice-approval.bpmn"]["primary"] is True
    assert "invoice-form-schema.json" in names
    assert names["invoice-form-schema.json"]["primary"] is False
    assert "process_model.json" not in names


def test_detail_when_bpmn_filename_differs_from_model_id(client, db_session, tmp_path, monkeypatch):
    """Template-created models keep the template BPMN name, not {leaf-id}.bpmn."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    model_dir = tmp_path / "bpmn" / "t1" / "test-process-group" / "wfh-group-4355dd7e70"
    model_dir.mkdir(parents=True)
    (tmp_path / "bpmn" / "t1" / "test-process-group" / "process_group.json").write_text(
        json.dumps({"display_name": "Test process group"}),
        encoding="utf-8",
    )
    (model_dir / "wfh-approval.bpmn").write_text(
        '<?xml version="1.0"?><definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"/>',
        encoding="utf-8",
    )
    (model_dir / "process_model.json").write_text(
        json.dumps(
            {
                "display_name": "WFH approval",
                "primary_file_name": "wfh-approval.bpmn",
            }
        ),
        encoding="utf-8",
    )
    _user, token = _login_user(
        client, db_session, username="editor-wfh", groups=["t1:editor"], tenant_id="t1"
    )

    listed = client.get(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert "test-process-group/wfh-group-4355dd7e70" in {
        row["id"] for row in listed.get_json()
    }

    response = client.get(
        "/v1.0/m8flow/process-models/test-process-group:wfh-group-4355dd7e70",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["id"] == "test-process-group/wfh-group-4355dd7e70"
    assert body["display_name"] == "WFH approval"
    names = {f["name"]: f for f in body["files"]}
    assert names["wfh-approval.bpmn"]["primary"] is True

    encoded = client.get(
        "/v1.0/m8flow/process-models/test-process-group%3Awfh-group-4355dd7e70",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert encoded.status_code == 200
    assert encoded.get_json()["id"] == "test-process-group/wfh-group-4355dd7e70"


def test_editor_saves_bpmn_file_with_a_non_leaf_name_writes_only_the_real_file(
    client, db_session, tmp_path, monkeypatch
):
    """Regression for architecture review finding W2: catalog._model_file_path
    used to hard-code {model-id-leaf}.bpmn regardless of the file actually
    being written, so every edit to a template-created model (which keeps its
    template's original filename, e.g. wfh-approval.bpmn under model id
    wfh-group-4355dd7e70) wrote the real file *and* a phantom
    wfh-group-4355dd7e70.bpmn alongside it."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    model_dir = tmp_path / "bpmn" / "t1" / "test-process-group" / "wfh-group-4355dd7e70"
    model_dir.mkdir(parents=True)
    (tmp_path / "bpmn" / "t1" / "test-process-group" / "process_group.json").write_text(
        json.dumps({"display_name": "Test process group"}),
        encoding="utf-8",
    )
    (model_dir / "wfh-approval.bpmn").write_text(
        '<?xml version="1.0"?><definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"/>',
        encoding="utf-8",
    )
    (model_dir / "process_model.json").write_text(
        json.dumps({"display_name": "WFH approval", "primary_file_name": "wfh-approval.bpmn"}),
        encoding="utf-8",
    )
    _user, token = _login_user(
        client, db_session, username="editor-wfh-save", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    xml = VALID_BPMN.read_bytes()

    response = client.put(
        "/v1.0/m8flow/process-models/test-process-group:wfh-group-4355dd7e70/files/wfh-approval.bpmn",
        data=xml,
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/octet-stream",
    )
    assert response.status_code == 200

    assert model_dir.joinpath("wfh-approval.bpmn").read_bytes() == xml
    phantom = model_dir / "wfh-group-4355dd7e70.bpmn"
    assert not phantom.exists(), "save() must not write a leaf-name-guessed phantom file"
    assert sorted(p.name for p in model_dir.glob("*.bpmn")) == ["wfh-approval.bpmn"]


def test_detail_missing_model_is_404(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor-missing", groups=["t1:editor"], tenant_id="t1"
    )

    response = client.get(
        "/v1.0/m8flow/process-models/finance:does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.get_json()["error_code"] == "not_found"


def test_reviewer_detail_is_404(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="reviewer-detail", groups=["t1:reviewer"], tenant_id="t1"
    )

    response = client.get(
        "/v1.0/m8flow/process-models/finance:invoice-approval",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.get_json()["error_code"] == "not_found"


def test_editor_reads_process_model_file_content(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor-file-read", groups=["t1:editor"], tenant_id="t1"
    )

    bpmn = client.get(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-approval.bpmn",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bpmn.status_code == 200
    assert bpmn.mimetype == "application/xml"
    assert b"<?xml" in bpmn.data

    schema = client.get(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-form-schema.json",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert schema.status_code == 200
    assert schema.mimetype == "application/json"
    assert schema.data == b"{}"


def test_read_file_missing_file_or_model_is_404(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor-file-404", groups=["t1:editor"], tenant_id="t1"
    )

    missing_file = client.get(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/does-not-exist.bpmn",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing_file.status_code == 404
    assert missing_file.get_json()["error_code"] == "not_found"

    missing_model = client.get(
        "/v1.0/m8flow/process-models/finance:does-not-exist/files/whatever.bpmn",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing_model.status_code == 404


def test_reviewer_read_file_is_404(client, db_session, tmp_path, monkeypatch):
    """Same 404-for-denied convention as the detail endpoint, not 403."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="reviewer-file", groups=["t1:reviewer"], tenant_id="t1"
    )

    response = client.get(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-approval.bpmn",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_read_file_path_traversal_is_rejected(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor-traversal", groups=["t1:editor"], tenant_id="t1"
    )

    response = client.get(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/sub/evil.txt",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_file_name"


def test_editor_saves_non_bpmn_file_without_git_commit(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor-save-json", groups=["t1:editor"], tenant_id="t1"
    )
    model_dir = tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval"
    subprocess_run = __import__("subprocess").run
    subprocess_run(["git", "init"], cwd=model_dir, capture_output=True)
    subprocess_run(["git", "config", "user.email", "test@example.test"], cwd=model_dir, capture_output=True)
    subprocess_run(["git", "config", "user.name", "Test"], cwd=model_dir, capture_output=True)

    response = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-form-schema.json",
        data=b'{"updated": true}',
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/octet-stream",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["name"] == "invoice-form-schema.json"
    assert body["size_bytes"] == len(b'{"updated": true}')

    saved = (model_dir / "invoice-form-schema.json").read_text(encoding="utf-8")
    assert saved == '{"updated": true}'

    log = subprocess_run(
        ["git", "log", "--oneline"], cwd=model_dir, capture_output=True, text=True
    )
    assert log.returncode != 0
    assert "invoice-form-schema.json" not in log.stdout


def test_editor_saves_bpmn_file_reimports_definition(client, db_session, tmp_path, monkeypatch):
    """Re-importing a .bpmn file goes through workflow.import_definition, which
    enforces m8flow-bpmn-core's own V1 "admin"-role command RBAC
    (process_definition.import) — a separate layer from the editor/tenant-admin
    URI-based groups this endpoint's own allow_uri() gate checks (see
    test_workflow_operations.py's _seed_actor, which grants role_name="admin"
    for the same reason). v1_role="user" (this file's default) 403s here even
    though the very same editor group succeeds for a non-bpmn file above —
    logged as a real, pre-existing gap in this ticket's answer, not fixed here.
    """
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client,
        db_session,
        username="editor-save-bpmn",
        groups=["t1:editor"],
        tenant_id="t1",
        v1_role="admin",
    )
    xml = VALID_BPMN.read_bytes()

    response = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-approval.bpmn",
        data=xml,
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/octet-stream",
    )
    assert response.status_code == 200

    model_dir = tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval"
    assert model_dir.joinpath("invoice-approval.bpmn").read_bytes() == xml


def test_editor_without_v1_admin_role_cannot_save_bpmn(client, db_session, tmp_path, monkeypatch):
    """Pins the gap documented on test_editor_saves_bpmn_file_reimports_definition:
    the editor group alone is not sufficient for .bpmn saves specifically —
    core's V1 "admin" role is also required. Non-bpmn saves are unaffected
    (see test_editor_saves_non_bpmn_file_without_git_commit, same group, no
    v1_role override, 200)."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor-no-v1-admin", groups=["t1:editor"], tenant_id="t1"
    )

    response = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-approval.bpmn",
        data=VALID_BPMN.read_bytes(),
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/octet-stream",
    )
    assert response.status_code == 403
    assert response.get_json()["error_code"] == "permission_denied"


def test_save_file_missing_model_is_404(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor-save-404", groups=["t1:editor"], tenant_id="t1"
    )

    response = client.put(
        "/v1.0/m8flow/process-models/finance:does-not-exist/files/whatever.json",
        data=b"{}",
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/octet-stream",
    )
    assert response.status_code == 404


def test_save_file_empty_body_is_400(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor-save-empty", groups=["t1:editor"], tenant_id="t1"
    )

    response = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-form-schema.json",
        data=b"",
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/octet-stream",
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "missing_content"


def test_save_file_path_traversal_is_rejected(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="editor-save-traversal", groups=["t1:editor"], tenant_id="t1"
    )

    # A non-leaf (slash-bearing) file name must be rejected by the controller's
    # validate_leaf_file_name guard. NB: a literal "../" vector is collapsed by
    # the ASGI transport (Starlette/uvicorn, like most HTTP clients/proxies)
    # before it reaches the app, so a subdir-style name is the vector that
    # actually exercises the guard here.
    response = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/sub/evil.json",
        data=b"{}",
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/octet-stream",
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_file_name"


def test_reviewer_save_file_is_403(client, db_session, tmp_path, monkeypatch):
    """Write op: denied is 403, unlike the read endpoints' 404-for-denied."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="reviewer-save", groups=["t1:reviewer"], tenant_id="t1"
    )

    response = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-form-schema.json",
        data=b"{}",
        headers={"Authorization": f"Bearer {token}"},
        content_type="application/octet-stream",
    )
    assert response.status_code == 403
    assert response.get_json()["error_code"] == "permission_denied"


def _import_definition(db_session, *, tenant_id: str, user_id: int, model_id: str) -> None:
    """Import a real BPMN definition so workflow.start can resolve one."""
    from m8flow_backend import workflow

    workflow.import_definition(
        db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        bpmn_identifier=model_id,
        source_bpmn_xml=VALID_BPMN.read_text(encoding="utf-8"),
        bpmn_name=f"{model_id.split('/')[-1]}.bpmn",
    )
    db_session.commit()


def test_editor_starts_process_instance(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="starter", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    _import_definition(db_session, tenant_id="t1", user_id=user.id, model_id="finance/invoice-approval")

    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["process_model_identifier"] == "finance/invoice-approval"
    assert isinstance(body["id"], int)

    # The instance is really persisted and tenant-scoped.
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    instance = db_session.get(ProcessInstanceModel, body["id"])
    assert instance is not None
    assert instance.m8f_tenant_id == "t1"
    assert instance.process_model_identifier == "finance/invoice-approval"


def test_start_is_refused_while_model_is_paused(client, db_session, tmp_path, monkeypatch):
    """Pausing blocks new starts (M8F-508). Guarded in workflow.start, so the
    thin/MCP start path is covered by the same rule, not just this route."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="starter-paused", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    _import_definition(db_session, tenant_id="t1", user_id=user.id, model_id="finance/invoice-approval")
    headers = {"Authorization": f"Bearer {token}"}

    paused = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval",
        headers=headers,
        json={"status": "paused"},
    )
    assert paused.status_code == 200, paused.get_json()

    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/start",
        headers=headers,
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "process_model_not_startable"

    # Republishing makes it startable again — pause is reversible.
    resumed = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval",
        headers=headers,
        json={"status": "published"},
    )
    assert resumed.status_code == 200
    assert (
        client.post(
            "/v1.0/m8flow/process-models/finance:invoice-approval/start", headers=headers
        ).status_code
        == 201
    )


def test_start_is_refused_while_model_is_draft(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="starter-draft", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    _import_definition(db_session, tenant_id="t1", user_id=user.id, model_id="onboarding/new-hire")

    response = client.post(
        "/v1.0/m8flow/process-models/onboarding:new-hire/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "process_model_not_startable"


def test_pausing_does_not_disturb_running_instances(client, db_session, tmp_path, monkeypatch):
    """Pause blocks new starts only; work already in flight is untouched."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="pause-inflight", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    _import_definition(db_session, tenant_id="t1", user_id=user.id, model_id="finance/invoice-approval")
    headers = {"Authorization": f"Bearer {token}"}

    started = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/start", headers=headers
    )
    assert started.status_code == 201
    instance_id = started.get_json()["id"]

    assert (
        client.put(
            "/v1.0/m8flow/process-models/finance:invoice-approval",
            headers=headers,
            json={"status": "paused"},
        ).status_code
        == 200
    )

    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    db_session.expire_all()
    instance = db_session.get(ProcessInstanceModel, instance_id)
    assert instance is not None
    assert instance.status not in ("terminated", "suspended")


def test_update_process_model_rejects_invalid_status_transition(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="status-writer", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}

    # onboarding/new-hire is draft; draft -> paused is not a legal pair.
    bad = client.put(
        "/v1.0/m8flow/process-models/onboarding:new-hire",
        headers=headers,
        json={"status": "paused"},
    )
    assert bad.status_code == 400
    assert bad.get_json()["error_code"] == "invalid_status_transition"

    # An unknown status is rejected by the api.yml enum before it reaches the
    # catalog; catalog's own invalid_status check still covers direct/MCP
    # callers that don't go through the schema (see the catalog status tests).
    unknown = client.put(
        "/v1.0/m8flow/process-models/onboarding:new-hire",
        headers=headers,
        json={"status": "archived"},
    )
    assert unknown.status_code == 400


def test_start_missing_model_is_404(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="starter2", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:does-not-exist/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_reviewer_cannot_start_process_instance(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="reviewer-start", groups=["t1:reviewer"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_editor_deletes_process_model(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="deleter", groups=["t1:editor"], tenant_id="t1"
    )
    model_dir = tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval"
    assert model_dir.is_dir()

    response = client.delete(
        "/v1.0/m8flow/process-models/finance:invoice-approval",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"deleted": True, "id": "finance/invoice-approval"}
    assert not model_dir.exists()


def test_delete_blocked_when_instances_exist(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="deleter2", groups=["t1:editor"], tenant_id="t1"
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
    )
    db_session.commit()

    response = client.delete(
        "/v1.0/m8flow/process-models/finance:invoice-approval",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "process_model_has_instances"
    # Model is untouched on disk.
    assert (tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval").is_dir()


def test_delete_missing_model_is_404(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="deleter3", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.delete(
        "/v1.0/m8flow/process-models/finance:nope",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_reviewer_cannot_delete_process_model(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="reviewer-del", groups=["t1:reviewer"], tenant_id="t1"
    )
    response = client.delete(
        "/v1.0/m8flow/process-models/finance:invoice-approval",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert (tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval").is_dir()


# Minimal BPMN that imports fine but has no start event, so starting it raises
# SpiffWorkflow's ValidationException("No start event found.") — which the host
# must surface as a clean 422, not a 500.
_NO_START_EVENT_BPMN = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
    'id="Defs_nostart" targetNamespace="http://bpmn.io/schema/bpmn">'
    '<bpmn:process id="finance/invoice-approval" isExecutable="true">'
    '<bpmn:task id="Task_1" name="Orphan task" />'
    '</bpmn:process>'
    '</bpmn:definitions>'
)


def test_start_unstartable_model_maps_to_422(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    from m8flow_backend import workflow

    user, token = _login_user(
        client, db_session, username="starter-nostart", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    workflow.import_definition(
        db_session,
        tenant_id="t1",
        user_id=user.id,
        bpmn_identifier="finance/invoice-approval",
        source_bpmn_xml=_NO_START_EVENT_BPMN,
        bpmn_name="invoice-approval.bpmn",
    )
    db_session.commit()

    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert response.get_json()["error_code"] == "invalid_process_model"


def test_editor_creates_edits_and_deletes_process_group(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="group-writer", groups=["t1:editor"], tenant_id="t1"
    )
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/v1.0/m8flow/process-groups",
        headers=headers,
        json={"id": "legal", "display_name": "Legal", "description": "Contracts"},
    )
    assert created.status_code == 201
    body = created.get_json()
    assert body["id"] == "legal"
    assert body["display_name"] == "Legal"
    assert body["description"] == "Contracts"
    assert body["model_count"] == 0
    group_dir = tmp_path / "bpmn" / "t1" / "legal"
    assert (group_dir / "process_group.json").is_file()

    nested = client.post(
        "/v1.0/m8flow/process-groups",
        headers=headers,
        json={"id": "finance/ap"},
    )
    assert nested.status_code == 201
    assert nested.get_json()["id"] == "finance/ap"
    assert nested.get_json()["display_name"] == "ap"

    updated = client.put(
        "/v1.0/m8flow/process-groups/legal",
        headers=headers,
        json={"display_name": "Legal Ops", "description": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["display_name"] == "Legal Ops"

    deleted = client.delete(
        "/v1.0/m8flow/process-groups/legal",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.get_json() == {"deleted": True, "id": "legal"}
    assert not group_dir.exists()


def test_create_process_group_rejects_duplicate_and_model_id(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="group-dup", groups=["t1:editor"], tenant_id="t1"
    )
    headers = {"Authorization": f"Bearer {token}"}

    duplicate = client.post(
        "/v1.0/m8flow/process-groups",
        headers=headers,
        json={"id": "finance"},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error_code"] == "process_group_exists"

    as_model = client.post(
        "/v1.0/m8flow/process-groups",
        headers=headers,
        json={"id": "finance/invoice-approval"},
    )
    assert as_model.status_code == 409
    assert as_model.get_json()["error_code"] == "process_model_exists"


def test_create_process_group_rejects_path_traversal(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="group-trav", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-groups",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "../t2/evil"},
    )
    assert response.status_code == 400
    assert not (tmp_path / "bpmn" / "t2" / "evil").exists()


def test_delete_process_group_blocked_when_instances_exist(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="group-del-inst", groups=["t1:editor"], tenant_id="t1"
    )
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="finance/invoice-approval",
        start=int(time.time()),
    )
    db_session.commit()

    response = client.delete(
        "/v1.0/m8flow/process-groups/finance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "process_group_has_instances"
    assert (tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval").is_dir()


def test_editor_deletes_empty_process_group(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="group-empty-del", groups=["t1:editor"], tenant_id="t1"
    )
    archived = tmp_path / "bpmn" / "t1" / "archived"
    assert archived.is_dir()
    response = client.delete(
        "/v1.0/m8flow/process-groups/archived",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert not archived.exists()


def test_viewer_cannot_create_process_group(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="group-viewer", groups=["t1:viewer"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-groups",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "legal"},
    )
    assert response.status_code == 403
    assert not (tmp_path / "bpmn" / "t1" / "legal").exists()


def test_super_admin_can_create_process_group_with_concrete_tenant(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="group-sa", groups=["super-admin"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-groups?tenantId=t1",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "legal", "m8f_tenant_id": "t1"},
    )
    assert response.status_code == 201, response.get_json()
    assert (tmp_path / "bpmn" / "t1" / "legal" / "process_group.json").is_file()


def test_super_admin_catalog_write_requires_concrete_tenant(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="group-sa-notenant", groups=["super-admin"], tenant_id="t1"
    )
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)
    response = client.post(
        "/v1.0/m8flow/process-groups",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "legal"},
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_required"
    assert not (tmp_path / "bpmn" / "t1" / "legal").exists()


def test_super_admin_catalog_write_rejects_conflicting_body_tenant(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="group-sa-conflict", groups=["super-admin"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-groups?tenantId=t1",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "legal", "m8f_tenant_id": "t2"},
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_override_forbidden"
    assert not (tmp_path / "bpmn" / "t1" / "legal").exists()
    assert not (tmp_path / "bpmn" / "t2" / "legal").exists()


def test_process_group_writes_stay_in_the_active_tenant(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="group-iso", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-groups",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "legal"},
    )
    assert response.status_code == 201
    assert (tmp_path / "bpmn" / "t1" / "legal" / "process_group.json").is_file()
    assert not (tmp_path / "bpmn" / "t2" / "legal").exists()


def test_editor_creates_and_updates_process_model(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-writer", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/v1.0/m8flow/process-models",
        headers=headers,
        json={
            "group_id": "finance",
            "id": "expense-report",
            "display_name": "Expense Report",
            "description": "Submit expenses",
        },
    )
    assert created.status_code == 201, created.get_json()
    body = created.get_json()
    assert body["id"] == "finance/expense-report"
    assert body["display_name"] == "Expense Report"
    assert body["group_id"] == "finance"
    model_dir = tmp_path / "bpmn" / "t1" / "finance" / "expense-report"
    bpmn = model_dir / "expense-report.bpmn"
    assert bpmn.is_file()
    xml = bpmn.read_text(encoding="utf-8")
    assert "StartEvent_1" in xml
    assert 'id="expense-report"' in xml

    updated = client.put(
        "/v1.0/m8flow/process-models/finance:expense-report",
        headers=headers,
        json={"display_name": "Expenses", "description": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["display_name"] == "Expenses"
    assert updated.get_json()["description"] == "Updated"


def test_create_process_model_slugifies_id_from_display_name(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-slug", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    response = client.post(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "finance", "display_name": "Expense Report"},
    )
    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    assert body["id"] == "finance/expense-report"
    assert body["display_name"] == "Expense Report"
    assert (tmp_path / "bpmn" / "t1" / "finance" / "expense-report" / "expense-report.bpmn").is_file()


def test_create_process_model_requires_id_or_display_name(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-noid", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "finance"},
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_process_model"


def test_create_process_model_requires_existing_group(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-nogroup", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "missing", "id": "x"},
    )
    assert response.status_code == 404


def test_create_process_model_rejects_duplicate(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-dup", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "finance", "id": "invoice-approval"},
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "process_model_exists"


def test_create_process_model_cleans_up_fs_when_bpmn_write_fails(
    client, db_session, tmp_path, monkeypatch
):
    """If write_spec_file raises after metadata mkdir, the orphaned dir must be removed
    so a retry is not blocked by target.exists() / process_model_exists."""
    import m8flow_backend.catalog as catalog_mod

    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client,
        db_session,
        username="model-write-fail",
        groups=["t1:editor"],
        tenant_id="t1",
        v1_role="admin",
    )
    headers = {"Authorization": f"Bearer {token}"}
    model_dir = tmp_path / "bpmn" / "t1" / "finance" / "orphan-probe"
    real_write = catalog_mod.write_spec_file

    def _fail_write(*, tenant_id: str, path: str, file_name: str, content: bytes):
        raise OSError("injected write_spec_file failure")

    monkeypatch.setattr(catalog_mod, "write_spec_file", _fail_write)
    failed = client.post(
        "/v1.0/m8flow/process-models",
        headers=headers,
        json={"group_id": "finance", "id": "orphan-probe"},
    )
    assert failed.status_code == 500
    assert not model_dir.exists()

    monkeypatch.setattr(catalog_mod, "write_spec_file", real_write)
    retry = client.post(
        "/v1.0/m8flow/process-models",
        headers=headers,
        json={"group_id": "finance", "id": "orphan-probe"},
    )
    assert retry.status_code == 201, retry.get_json()
    assert (model_dir / "orphan-probe.bpmn").is_file()


def test_update_process_model_primary_file(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-primary", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models",
        headers=headers,
        json={"group_id": "archived", "id": "notes"},
    )
    assert created.status_code == 201, created.get_json()
    model_dir = tmp_path / "bpmn" / "t1" / "archived" / "notes"
    (model_dir / "other.bpmn").write_text(model_dir.joinpath("notes.bpmn").read_text(encoding="utf-8"), encoding="utf-8")

    ok = client.put(
        "/v1.0/m8flow/process-models/archived:notes",
        headers=headers,
        json={"primary_file_name": "other.bpmn"},
    )
    assert ok.status_code == 200
    missing = client.put(
        "/v1.0/m8flow/process-models/archived:notes",
        headers=headers,
        json={"primary_file_name": "nope.bpmn"},
    )
    assert missing.status_code == 400
    assert missing.get_json()["error_code"] == "invalid_primary_file"


def test_viewer_cannot_create_process_model(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-viewer", groups=["t1:viewer"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "finance", "id": "x"},
    )
    assert response.status_code == 403


def test_super_admin_can_create_process_model_with_concrete_tenant(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client,
        db_session,
        username="model-sa",
        groups=["super-admin"],
        tenant_id="t1",
        v1_role="admin",
    )
    response = client.post(
        "/v1.0/m8flow/process-models?tenantId=t1",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "finance", "id": "sa-model", "m8f_tenant_id": "t1"},
    )
    assert response.status_code == 201, response.get_json()
    assert (tmp_path / "bpmn" / "t1" / "finance" / "sa-model" / "sa-model.bpmn").is_file()


def test_super_admin_create_process_model_without_tenant_is_400(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-sa-notenant", groups=["super-admin"], tenant_id="t1"
    )
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)
    response = client.post(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "finance", "id": "x"},
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_required"
    assert not (tmp_path / "bpmn" / "t1" / "finance" / "x").exists()


def test_process_model_create_stays_in_the_active_tenant(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="model-iso", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    response = client.post(
        "/v1.0/m8flow/process-models",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "finance", "id": "only-t1"},
    )
    assert response.status_code == 201, response.get_json()
    assert (tmp_path / "bpmn" / "t1" / "finance" / "only-t1" / "only-t1.bpmn").is_file()
    assert not (tmp_path / "bpmn" / "t2" / "finance" / "only-t1").exists()


def test_editor_copies_process_model_files_not_instances(client, db_session, tmp_path, monkeypatch):
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="model-copy", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models",
        headers=headers,
        json={
            "group_id": "archived",
            "id": "notes",
            "display_name": "Notes",
            "description": "Keep me",
        },
    )
    assert created.status_code == 201, created.get_json()
    added = client.post(
        "/v1.0/m8flow/process-models/archived:notes/files",
        headers=headers,
        json={"file_name": "notes.md"},
    )
    assert added.status_code == 201, added.get_json()
    _seed_instance(
        db_session,
        tenant_id="t1",
        initiator_id=user.id,
        process_model_identifier="archived/notes",
        start=int(time.time()),
    )
    db_session.commit()

    copied = client.post(
        "/v1.0/m8flow/process-models/archived:notes/copy",
        headers=headers,
        json={"id": "notes-copy", "display_name": "Notes copy"},
    )
    assert copied.status_code == 201, copied.get_json()
    body = copied.get_json()
    assert body["id"] == "archived/notes-copy"
    assert body["display_name"] == "Notes copy"
    assert body["description"] == "Keep me"
    assert body["group_id"] == "archived"
    dest = tmp_path / "bpmn" / "t1" / "archived" / "notes-copy"
    assert (dest / "notes.bpmn").is_file()
    assert (dest / "notes.md").is_file()
    assert (tmp_path / "bpmn" / "t1" / "archived" / "notes" / "notes.bpmn").is_file()
    meta = json.loads((dest / "process_model.json").read_text(encoding="utf-8"))
    assert meta["display_name"] == "Notes copy"
    assert meta["primary_file_name"] == "notes.bpmn"
    source_count = db_session.query(ProcessInstanceModel).filter_by(
        m8f_tenant_id="t1", process_model_identifier="archived/notes"
    ).count()
    dest_count = db_session.query(ProcessInstanceModel).filter_by(
        m8f_tenant_id="t1", process_model_identifier="archived/notes-copy"
    ).count()
    assert source_count == 1
    assert dest_count == 0


def test_copy_process_model_rejects_duplicate(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-copy-dup", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/copy",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "invoice-approval"},
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "process_model_exists"


def test_copy_process_model_missing_source_is_404(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-copy-404", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:missing/copy",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "notes-copy"},
    )
    assert response.status_code == 404


def test_viewer_cannot_copy_process_model(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="model-copy-viewer", groups=["t1:viewer"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/copy",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "x"},
    )
    assert response.status_code == 403
    assert not (tmp_path / "bpmn" / "t1" / "finance" / "x").exists()


def test_super_admin_can_copy_process_model_with_concrete_tenant(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client,
        db_session,
        username="model-copy-sa",
        groups=["super-admin"],
        tenant_id="t1",
        v1_role="admin",
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models?tenantId=t1",
        headers=headers,
        json={
            "group_id": "archived",
            "id": "notes",
            "display_name": "Notes",
            "m8f_tenant_id": "t1",
        },
    )
    assert created.status_code == 201, created.get_json()
    response = client.post(
        "/v1.0/m8flow/process-models/archived:notes/copy?tenantId=t1",
        headers=headers,
        json={"id": "sa-copy", "display_name": "SA copy", "m8f_tenant_id": "t1"},
    )
    assert response.status_code == 201, response.get_json()
    assert (tmp_path / "bpmn" / "t1" / "archived" / "sa-copy" / "notes.bpmn").is_file()


def test_process_model_copy_stays_in_the_active_tenant(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="model-copy-iso", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models",
        headers=headers,
        json={"group_id": "archived", "id": "notes"},
    )
    assert created.status_code == 201, created.get_json()
    response = client.post(
        "/v1.0/m8flow/process-models/archived:notes/copy",
        headers=headers,
        json={"id": "only-t1"},
    )
    assert response.status_code == 201, response.get_json()
    assert (tmp_path / "bpmn" / "t1" / "archived" / "only-t1" / "notes.bpmn").is_file()
    assert not (tmp_path / "bpmn" / "t2" / "archived" / "only-t1").exists()


_SCRIPT_BPMN = """\
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="scripted" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:scriptTask id="Script_1" name="Set x">
      <bpmn:incoming>Flow_1</bpmn:incoming>
      <bpmn:outgoing>Flow_2</bpmn:outgoing>
      <bpmn:script>x = 1</bpmn:script>
    </bpmn:scriptTask>
    <bpmn:endEvent id="EndEvent_1">
      <bpmn:incoming>Flow_2</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Script_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Script_1" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>
"""


def test_editor_runs_bpmn_unit_tests(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="bpmn-tests", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models",
        headers=headers,
        json={"group_id": "archived", "id": "notes"},
    )
    assert created.status_code == 201, created.get_json()
    added = client.post(
        "/v1.0/m8flow/process-models/archived:notes/files",
        headers=headers,
        json={
            "file_name": "test_notes.json",
            "content": json.dumps({"happy_path": {"expected_output_json": {}}}),
        },
    )
    assert added.status_code == 201, added.get_json()
    ran = client.post(
        "/v1.0/m8flow/process-models/archived:notes/tests/run",
        headers=headers,
    )
    assert ran.status_code == 200, ran.get_json()
    body = ran.get_json()
    assert body["all_passed"] is True
    assert len(body["passing"]) == 1
    assert body["passing"][0]["test_case_identifier"] == "happy_path"


def test_bpmn_unit_test_failure_is_reported(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="bpmn-tests-fail", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models",
        headers=headers,
        json={"group_id": "archived", "id": "notes"},
    )
    assert created.status_code == 201, created.get_json()
    client.post(
        "/v1.0/m8flow/process-models/archived:notes/files",
        headers=headers,
        json={
            "file_name": "test_notes.json",
            "content": json.dumps({"mismatch": {"expected_output_json": {"x": 1}}}),
        },
    )
    ran = client.post(
        "/v1.0/m8flow/process-models/archived:notes/tests/run",
        headers=headers,
    )
    assert ran.status_code == 200, ran.get_json()
    body = ran.get_json()
    assert body["all_passed"] is False
    assert body["failing"][0]["test_case_identifier"] == "mismatch"


def test_viewer_cannot_run_bpmn_unit_tests(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="bpmn-tests-viewer", groups=["t1:viewer"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/tests/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_super_admin_can_run_bpmn_unit_tests_with_concrete_tenant(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client,
        db_session,
        username="bpmn-tests-sa",
        groups=["super-admin"],
        tenant_id="t1",
        v1_role="admin",
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models?tenantId=t1",
        headers=headers,
        json={"group_id": "archived", "id": "notes", "m8f_tenant_id": "t1"},
    )
    assert created.status_code == 201, created.get_json()
    added = client.post(
        "/v1.0/m8flow/process-models/archived:notes/files?tenantId=t1",
        headers=headers,
        json={
            "file_name": "test_notes.json",
            "content": json.dumps({"happy_path": {"expected_output_json": {}}}),
            "m8f_tenant_id": "t1",
        },
    )
    assert added.status_code == 201, added.get_json()
    response = client.post(
        "/v1.0/m8flow/process-models/archived:notes/tests/run?tenantId=t1",
        headers=headers,
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["all_passed"] is True


def test_bpmn_unit_tests_404_without_test_files(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="bpmn-tests-empty", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/tests/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.get_json()["error_code"] == "no_test_cases"


def test_editor_creates_and_runs_script_unit_test(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="script-tests", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models",
        headers=headers,
        json={"group_id": "archived", "id": "scripted"},
    )
    assert created.status_code == 201, created.get_json()
    model_dir = tmp_path / "bpmn" / "t1" / "archived" / "scripted"
    (model_dir / "scripted.bpmn").write_text(_SCRIPT_BPMN, encoding="utf-8")

    created_test = client.post(
        "/v1.0/m8flow/process-models/archived:scripted/script-unit-tests",
        headers=headers,
        json={
            "bpmn_task_identifier": "Script_1",
            "input_json": {},
            "expected_output_json": {"x": 1},
        },
    )
    assert created_test.status_code == 201, created_test.get_json()
    unit_id = created_test.get_json()["id"]
    listed = client.get(
        "/v1.0/m8flow/process-models/archived:scripted/script-unit-tests",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.get_json()["tests"][0]["id"] == unit_id
    stored = client.post(
        "/v1.0/m8flow/process-models/archived:scripted/script-unit-tests/run",
        headers=headers,
        json={"unit_test_id": unit_id},
    )
    assert stored.status_code == 200, stored.get_json()
    assert stored.get_json()["result"] is True
    ad_hoc = client.post(
        "/v1.0/m8flow/process-models/archived:scripted/script-unit-tests/run",
        headers=headers,
        json={"python_script": "x = 2", "input_json": {}, "expected_output_json": {"x": 2}},
    )
    assert ad_hoc.status_code == 200
    assert ad_hoc.get_json()["result"] is True


def test_super_admin_can_run_script_unit_test_with_concrete_tenant(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client,
        db_session,
        username="script-tests-sa",
        groups=["super-admin"],
        tenant_id="t1",
        v1_role="admin",
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/script-unit-tests/run?tenantId=t1",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "python_script": "x = 1",
            "input_json": {},
            "expected_output_json": {"x": 1},
            "m8f_tenant_id": "t1",
        },
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["result"] is True


def test_editor_adds_default_json_and_deletes_non_primary(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="file-add", groups=["t1:editor"], tenant_id="t1"
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files",
        headers=headers,
        json={"file_name": "notes.md"},
    )
    assert created.status_code == 201, created.get_json()
    assert created.get_json()["name"] == "notes.md"
    model_dir = tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval"
    assert (model_dir / "notes.md").is_file()

    deleted = client.delete(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/notes.md",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert not (model_dir / "notes.md").exists()


def test_editor_adds_default_bpmn_file(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client,
        db_session,
        username="file-add-bpmn",
        groups=["t1:editor"],
        tenant_id="t1",
        v1_role="admin",
    )
    created = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files",
        headers={"Authorization": f"Bearer {token}"},
        json={"file_name": "extra.bpmn"},
    )
    assert created.status_code == 201, created.get_json()
    xml = (tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval" / "extra.bpmn").read_text(
        encoding="utf-8"
    )
    assert "StartEvent_1" in xml
    assert 'id="extra"' in xml


def test_create_file_rejects_duplicate_and_reserved(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="file-dup", groups=["t1:editor"], tenant_id="t1"
    )
    headers = {"Authorization": f"Bearer {token}"}
    duplicate = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files",
        headers=headers,
        json={"file_name": "invoice-form-schema.json"},
    )
    assert duplicate.status_code == 409
    reserved = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files",
        headers=headers,
        json={"file_name": "process_model.json"},
    )
    assert reserved.status_code == 400
    assert reserved.get_json()["error_code"] == "reserved_file_name"


def test_delete_primary_file_is_409(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="file-del-primary", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.delete(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-approval.bpmn",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "cannot_delete_primary"


def test_viewer_cannot_add_or_delete_file(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="file-viewer", groups=["t1:viewer"], tenant_id="t1"
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files",
        headers=headers,
        json={"file_name": "notes.md"},
    )
    assert created.status_code == 403
    deleted = client.delete(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-form-schema.json",
        headers=headers,
    )
    assert deleted.status_code == 403


def test_super_admin_can_add_and_delete_file_with_concrete_tenant(
    client, db_session, tmp_path, monkeypatch
):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="file-sa", groups=["super-admin"], tenant_id="t1"
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files?tenantId=t1",
        headers=headers,
        json={"file_name": "notes.md", "m8f_tenant_id": "t1"},
    )
    assert created.status_code == 201, created.get_json()
    model_dir = tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval"
    assert (model_dir / "notes.md").is_file()
    deleted = client.delete(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/notes.md?tenantId=t1",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert not (model_dir / "notes.md").exists()
    assert (model_dir / "invoice-form-schema.json").is_file()


def test_create_file_stays_in_the_active_tenant(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="file-iso", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files",
        headers={"Authorization": f"Bearer {token}"},
        json={"file_name": "only-t1.md"},
    )
    assert response.status_code == 201, response.get_json()
    assert (tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval" / "only-t1.md").is_file()
    assert not (tmp_path / "bpmn" / "t2" / "finance" / "invoice-approval" / "only-t1.md").exists()


def test_create_file_upload_content(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="file-upload", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files",
        headers={"Authorization": f"Bearer {token}"},
        json={"file_name": "readme.txt", "content": "hello"},
    )
    assert response.status_code == 201, response.get_json()
    saved = tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval" / "readme.txt"
    assert saved.read_text(encoding="utf-8") == "hello"


def test_delete_file_path_traversal_is_rejected(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _user, token = _login_user(
        client, db_session, username="file-del-trav", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.delete(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/sub/evil.txt",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_file_name"


def test_super_admin_creates_model_in_a_tenant_they_never_logged_into(
    client, db_session, tmp_path, monkeypatch
):
    """The reported bug: super-admin logs into t1, a NEW tenant t2 is created
    (a bare tenant row -- no membership, no v1 role, exactly what
    keycloak_controller.create_realm leaves behind), then a model is created in
    t2. m8flow-bpmn-core's ensure_user_belongs_to_tenant used to 403 this with
    "User N does not belong to tenant t2": the super-admin's
    tenant_specific_field_1 is still t1 and their service realm is the shared
    realm, so neither intersects t2's {id, slug}.

    Note this cannot be written with _login_user(tenant_id="t2") -- that calls
    ensure_membership for t2 and hides the bug, which is why every existing
    super-admin write test passed.
    """
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    user, token = _login_user(
        client, db_session, username="sa-cross", groups=["super-admin"], tenant_id="t1"
    )
    # The new tenant exists, but nobody -- not even its creator -- is a member.
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()

    response = client.post(
        "/v1.0/m8flow/process-models?tenantId=t2",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "finance", "id": "sa-cross-model", "m8f_tenant_id": "t2"},
    )
    assert response.status_code == 201, response.get_json()
    assert (tmp_path / "bpmn" / "t2" / "finance" / "sa-cross-model" / "sa-cross-model.bpmn").is_file()

    # The scoped grant must not outlive the request: no persisted membership.
    db_session.expire_all()
    refreshed = db_session.get(type(user), user.id)
    assert refreshed.tenant_specific_field_3 is None
    assert refreshed.tenant_specific_field_1 == "t1"


def test_super_admin_saves_and_copies_in_another_tenant(
    client, db_session, tmp_path, monkeypatch
):
    """The fix sits in workflow.import_definition, the funnel every catalog
    write shares -- so saving a BPMN file and copying a model into a tenant the
    super-admin never logged into work too, not just create.
    """
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="sa-cross-write", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    saved = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-approval.bpmn?tenantId=t2",
        data=VALID_BPMN.read_bytes(),
        headers=headers,
        content_type="application/octet-stream",
    )
    assert saved.status_code == 200, saved.get_json()

    copied = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/copy?tenantId=t2",
        headers=headers,
        json={"group_id": "finance", "id": "invoice-copy", "m8f_tenant_id": "t2"},
    )
    assert copied.status_code == 201, copied.get_json()


def test_non_super_admin_still_cannot_write_into_another_tenant(
    client, db_session, tmp_path, monkeypatch
):
    """The membership scope is super-admin-only: a plain editor in t1 targeting
    t2 must still be refused. Guards tenant isolation against the fix above.
    """
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="editor-cross", groups=["t1:editor"], tenant_id="t1",
        v1_role="admin",
    )
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()

    response = client.post(
        "/v1.0/m8flow/process-models?tenantId=t2",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": "finance", "id": "editor-cross-model", "m8f_tenant_id": "t2"},
    )
    # The ?tenantId/body override is super-admin-only: require_catalog_write_tenant_id
    # ignores both for a regular user and falls back to their own cookie tenant.
    # So the write lands in t1 (their own tenant) and NEVER in t2 -- the editor
    # cannot reach another tenant, with or without the membership scope.
    # Nothing reaches t2, with or without the membership scope.
    assert not (tmp_path / "bpmn" / "t2" / "finance" / "editor-cross-model").exists()
    # The override is ignored rather than rejected: the write is redirected to
    # the editor's OWN cookie tenant, so the response is a 201 against t1.
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["tenant_id"] == "t1"
    assert (
        tmp_path / "bpmn" / "t1" / "finance" / "editor-cross-model" / "editor-cross-model.bpmn"
    ).is_file()


def test_super_admin_starts_instance_in_a_tenant_they_never_logged_into(
    client, db_session, tmp_path, monkeypatch
):
    """Start is a write like create: a super-admin acting in a tenant they did
    not log into must not hit core's tenant-membership guard."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="sa-start-cross", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    # Give t2 a real, startable definition first (also exercises the create fix).
    saved = client.put(
        "/v1.0/m8flow/process-models/finance:invoice-approval/files/invoice-approval.bpmn?tenantId=t2",
        data=VALID_BPMN.read_bytes(),
        headers=headers,
        content_type="application/octet-stream",
    )
    assert saved.status_code == 200, saved.get_json()

    started = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/start?tenantId=t2",
        headers=headers,
    )
    assert started.status_code == 201, started.get_json()


def test_super_admin_membership_scope_reverts_when_the_write_fails(
    client, db_session, tmp_path, monkeypatch
):
    """The scoped grant must be reverted even when the core command raises --
    otherwise a failed start would leave the super-admin a permanent member of
    the target tenant.
    """
    from m8flow_bpmn_core.models.user import UserModel

    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    user, token = _login_user(
        client, db_session, username="sa-revert", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()
    user_id = user.id

    # t2's seeded .bpmn is a stub with no start event, so core raises.
    response = client.post(
        "/v1.0/m8flow/process-models/finance:invoice-approval/start?tenantId=t2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code >= 400, response.get_json()

    db_session.expire_all()
    refreshed = db_session.get(UserModel, user_id)
    assert refreshed.tenant_specific_field_3 is None
    assert refreshed.tenant_specific_field_1 == "t1"
