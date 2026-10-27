"""Versioned publishing (Approach B): Draft -> Publish -> Edit -> Save -> Start ->
Publish Changes, plus History and Revert.

Saving changes only the working copy on disk; Start runs the newest live row
(publish / baseline) recorded in m8flow_process_model_version.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.identity import ensure_tenant

from .test_processes_controller import (
    _import_definition,
    _login_user,
    _seed_catalog,
)

VALID_BPMN = (Path(__file__).resolve().parents[3] / "fixtures" / "invoice_approval_poc.bpmn").read_text(
    encoding="utf-8"
)
CHANGED_BPMN = VALID_BPMN.replace('name="Approve"', 'name="Approve v2"')

DRAFT = "onboarding:new-hire"
DRAFT_FILE = "new-hire.bpmn"
LEGACY = "finance:invoice-approval"
LEGACY_FILE = "invoice-approval.bpmn"


def _editor(client, db_session, username: str = "versions-editor"):
    _user, token = _login_user(
        client, db_session, username=username, groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    return {"Authorization": f"Bearer {token}"}


def _put_file(client, headers, model: str, file_name: str, xml: str):
    response = client.put(
        f"/v1.0/m8flow/process-models/{model}/files/{file_name}",
        data=xml.encode("utf-8"),
        headers=headers,
        content_type="application/octet-stream",
    )
    assert response.status_code == 200, response.get_json()


def _set_status(client, headers, model: str, status: str) -> dict:
    response = client.put(f"/v1.0/m8flow/process-models/{model}", headers=headers, json={"status": status})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _detail(client, headers, model: str) -> dict:
    response = client.get(f"/v1.0/m8flow/process-models/{model}", headers=headers)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _history(client, headers, model: str, **params) -> dict:
    response = client.get(f"/v1.0/m8flow/process-models/{model}/versions", headers=headers, query_string=params)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _start_xml(client, headers, db_session, model: str) -> str:
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    response = client.post(f"/v1.0/m8flow/process-models/{model}/start", headers=headers)
    assert response.status_code == 201, response.get_json()
    db_session.expire_all()
    instance = db_session.get(ProcessInstanceModel, response.get_json()["id"])
    return db_session.get(BpmnProcessDefinitionModel, instance.bpmn_process_definition_id).source_bpmn_xml


def test_full_lifecycle_save_does_not_change_what_start_runs(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    headers = _editor(client, db_session)

    # Draft: save records history but nothing is live.
    _put_file(client, headers, DRAFT, DRAFT_FILE, VALID_BPMN)
    detail = _detail(client, headers, DRAFT)
    assert detail["status"] == "draft"
    assert detail["live_version"] is None
    assert detail["has_unpublished_changes"] is False

    # Publish makes the working copy live.
    published = _set_status(client, headers, DRAFT, "published")
    assert published["live_version"] == 2
    assert published["has_unpublished_changes"] is False
    assert _start_xml(client, headers, db_session, DRAFT) == VALID_BPMN

    # Edit + Save: still published, now with unpublished changes; Start runs the old XML.
    _put_file(client, headers, DRAFT, DRAFT_FILE, CHANGED_BPMN)
    detail = _detail(client, headers, DRAFT)
    assert detail["status"] == "published"
    assert detail["live_version"] == 2
    assert detail["has_unpublished_changes"] is True
    assert _start_xml(client, headers, db_session, DRAFT) == VALID_BPMN

    # Publish Changes: new live version, Start runs the new XML.
    republished = _set_status(client, headers, DRAFT, "published")
    assert republished["live_version"] == 4
    assert republished["has_unpublished_changes"] is False
    assert _start_xml(client, headers, db_session, DRAFT) == CHANGED_BPMN

    actions = [(row["version"], row["action"], row["is_live"]) for row in _history(client, headers, DRAFT)["results"]]
    assert actions == [(4, "publish", True), (3, "save", False), (2, "publish", False), (1, "save", False)]


def test_identical_save_and_double_publish_add_no_rows(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    headers = _editor(client, db_session, "versions-dedupe")

    _put_file(client, headers, DRAFT, DRAFT_FILE, VALID_BPMN)
    _put_file(client, headers, DRAFT, DRAFT_FILE, VALID_BPMN)
    _set_status(client, headers, DRAFT, "published")
    _set_status(client, headers, DRAFT, "published")

    history = _history(client, headers, DRAFT)
    assert [row["action"] for row in history["results"]] == ["publish", "save"]
    assert history["pagination"]["total"] == 2


def test_revert_restores_working_copy_without_going_live(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    headers = _editor(client, db_session, "versions-revert")
    model_file = tmp_path / "bpmn" / "t1" / "onboarding" / "new-hire" / DRAFT_FILE

    _put_file(client, headers, DRAFT, DRAFT_FILE, VALID_BPMN)
    _set_status(client, headers, DRAFT, "published")  # v2 live = VALID
    _put_file(client, headers, DRAFT, DRAFT_FILE, CHANGED_BPMN)
    _set_status(client, headers, DRAFT, "published")  # v4 live = CHANGED

    response = client.post(f"/v1.0/m8flow/process-models/{DRAFT}/versions/2/revert", headers=headers)
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["live_version"] == 4
    assert body["has_unpublished_changes"] is True
    assert model_file.read_text(encoding="utf-8") == VALID_BPMN
    assert _start_xml(client, headers, db_session, DRAFT) == CHANGED_BPMN

    newest = _history(client, headers, DRAFT)["results"][0]
    assert newest["action"] == "revert"
    assert newest["reverted_from_version"] == 2

    _set_status(client, headers, DRAFT, "published")
    assert _start_xml(client, headers, db_session, DRAFT) == VALID_BPMN


def test_revert_unknown_version_is_404(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    headers = _editor(client, db_session, "versions-revert-404")
    response = client.post(f"/v1.0/m8flow/process-models/{DRAFT}/versions/99/revert", headers=headers)
    assert response.status_code == 404


def test_pre_existing_published_model_keeps_running_its_old_xml(client, db_session, tmp_path, monkeypatch):
    """A model published before history existed is baselined before its first
    edit, so upgrading never changes what Start runs."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="versions-legacy", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}
    _import_definition(db_session, tenant_id="t1", user_id=user.id, model_id="finance/invoice-approval")

    _put_file(client, headers, LEGACY, LEGACY_FILE, CHANGED_BPMN)

    rows = _history(client, headers, LEGACY)["results"]
    assert [(row["action"], row["is_live"]) for row in rows] == [("save", False), ("baseline", True)]
    assert _detail(client, headers, LEGACY)["has_unpublished_changes"] is True
    assert _start_xml(client, headers, db_session, LEGACY) == VALID_BPMN


def test_start_without_history_runs_the_file_on_disk_and_records_nothing(
    client, db_session, tmp_path, monkeypatch
):
    """No live row means no in-app edit since history existed, so the file on disk
    is what the model runs. A plain Start stays read-only (no row, no commit)."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    user, token = _login_user(
        client, db_session, username="versions-baseline", groups=["t1:editor"], tenant_id="t1", v1_role="admin"
    )
    headers = {"Authorization": f"Bearer {token}"}
    _import_definition(db_session, tenant_id="t1", user_id=user.id, model_id="finance/invoice-approval")

    assert _start_xml(client, headers, db_session, LEGACY) == VALID_BPMN
    assert _history(client, headers, LEGACY)["results"] == []


def test_resume_from_pause_keeps_the_live_version(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    headers = _editor(client, db_session, "versions-pause")

    _put_file(client, headers, DRAFT, DRAFT_FILE, VALID_BPMN)
    _set_status(client, headers, DRAFT, "published")
    _put_file(client, headers, DRAFT, DRAFT_FILE, CHANGED_BPMN)
    _set_status(client, headers, DRAFT, "paused")
    resumed = _set_status(client, headers, DRAFT, "published")

    assert resumed["live_version"] == 2
    assert resumed["has_unpublished_changes"] is True
    assert _start_xml(client, headers, db_session, DRAFT) == VALID_BPMN


def test_list_carries_unpublished_changes_flag(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    headers = _editor(client, db_session, "versions-list")
    _put_file(client, headers, DRAFT, DRAFT_FILE, VALID_BPMN)
    _set_status(client, headers, DRAFT, "published")
    _put_file(client, headers, DRAFT, DRAFT_FILE, CHANGED_BPMN)

    response = client.get("/v1.0/m8flow/process-models", headers=headers)
    assert response.status_code == 200
    rows = {row["id"]: row for row in response.get_json()}
    assert rows["onboarding/new-hire"]["has_unpublished_changes"] is True
    assert rows["onboarding/new-hire"]["live_version"] == 2
    assert rows["finance/invoice-approval"]["live_version"] is None


def test_history_is_paged(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    headers = _editor(client, db_session, "versions-paged")
    for index in range(3):
        _put_file(client, headers, DRAFT, DRAFT_FILE, VALID_BPMN.replace('name="Approve"', f'name="A{index}"'))

    first = _history(client, headers, DRAFT, page=1, per_page=2)
    second = _history(client, headers, DRAFT, page=2, per_page=2)
    assert [row["version"] for row in first["results"]] == [3, 2]
    assert [row["version"] for row in second["results"]] == [1]
    assert first["pagination"] == {"page": 1, "per_page": 2, "total": 3, "pages": 2}


def test_viewer_reads_history_but_cannot_revert(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    editor_headers = _editor(client, db_session, "versions-owner")
    _put_file(client, editor_headers, DRAFT, DRAFT_FILE, VALID_BPMN)

    _viewer, token = _login_user(client, db_session, username="versions-viewer", groups=["t1:viewer"], tenant_id="t1")
    viewer_headers = {"Authorization": f"Bearer {token}"}

    assert client.get(f"/v1.0/m8flow/process-models/{DRAFT}/versions", headers=viewer_headers).status_code == 200
    denied = client.post(f"/v1.0/m8flow/process-models/{DRAFT}/versions/1/revert", headers=viewer_headers)
    assert denied.status_code == 403


def test_history_does_not_cross_tenants(client, db_session, tmp_path, monkeypatch):
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    editor_headers = _editor(client, db_session, "versions-t1")
    _put_file(client, editor_headers, DRAFT, DRAFT_FILE, VALID_BPMN)

    _other, token = _login_user(
        client, db_session, username="versions-t2", groups=["t2:editor"], tenant_id="t2", v1_role="admin"
    )
    other_headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/v1.0/m8flow/process-models/{DRAFT}/versions", headers=other_headers).status_code == 404
    assert (
        client.post(f"/v1.0/m8flow/process-models/{DRAFT}/versions/1/revert", headers=other_headers).status_code
        == 404
    )


def test_deleting_a_model_removes_its_history(client, db_session, tmp_path, monkeypatch):
    from m8flow_backend.models.process_model_version import ProcessModelVersionModel

    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    headers = _editor(client, db_session, "versions-delete")
    _put_file(client, headers, DRAFT, DRAFT_FILE, VALID_BPMN)

    assert client.delete(f"/v1.0/m8flow/process-models/{DRAFT}", headers=headers).status_code == 200
    db_session.expire_all()
    remaining = db_session.scalars(
        select(ProcessModelVersionModel).where(
            ProcessModelVersionModel.process_model_identifier == "onboarding/new-hire"
        )
    ).all()
    assert remaining == []


def test_super_admin_history_requires_a_concrete_tenant(client, db_session, tmp_path, monkeypatch):
    """Model ids collide across tenants, so All Tenants (no cookie, no tenantId)
    must not fan out and return whichever tenant's history it finds first."""
    from m8flow_backend.catalog import versions

    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(client, db_session, username="versions-sa", groups=["super-admin"], tenant_id="t1")
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    for tenant, author in (("t1", "alice"), ("t2", "bob")):
        versions.record(
            db_session,
            tenant_id=tenant,
            process_model_identifier="finance/invoice-approval",
            action=versions.ACTION_SAVE,
            created_by=author,
        )
    db_session.commit()
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)
    headers = {"Authorization": f"Bearer {token}"}

    ambiguous = client.get(f"/v1.0/m8flow/process-models/{LEGACY}/versions", headers=headers)
    assert ambiguous.status_code == 400
    assert ambiguous.get_json()["error_code"] == "tenant_required"

    scoped = _history(client, headers, LEGACY, tenantId="t2")
    assert [row["created_by"] for row in scoped["results"]] == ["bob"]


def test_revert_of_a_non_utf8_version_is_a_400_and_changes_nothing(client, db_session, tmp_path, monkeypatch):
    import base64

    from m8flow_backend.models.process_model_version import ProcessModelVersionModel

    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    headers = _editor(client, db_session, "versions-revert-utf8")
    _put_file(client, headers, DRAFT, DRAFT_FILE, VALID_BPMN)
    db_session.add(
        ProcessModelVersionModel(
            m8f_tenant_id="t1",
            process_model_identifier="onboarding/new-hire",
            version=2,
            action="save",
            files={DRAFT_FILE: {"base64": base64.b64encode(b"\xff\xfe<bpmn/>").decode("ascii")}},
            primary_file_name=DRAFT_FILE,
            digest="0" * 64,
            created_by="corrupt",
        )
    )
    db_session.commit()
    model_file = tmp_path / "bpmn" / "t1" / "onboarding" / "new-hire" / DRAFT_FILE

    response = client.post(f"/v1.0/m8flow/process-models/{DRAFT}/versions/2/revert", headers=headers)

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_file_content"
    assert model_file.read_text(encoding="utf-8") == VALID_BPMN
    assert [row["version"] for row in _history(client, headers, DRAFT)["results"]] == [2, 1]


def test_super_admin_reverts_only_the_tenant_named_by_tenant_id(client, db_session, tmp_path, monkeypatch):
    """Model ids collide across tenants: ?tenantId must pick the one tenant the
    revert writes to, and All Tenants without it must refuse (400)."""
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t1")
    _seed_catalog(tmp_path, monkeypatch, tenant_id="t2")
    _user, token = _login_user(
        client, db_session, username="versions-sa-revert", groups=["super-admin"], tenant_id="t1"
    )
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()
    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)
    headers = {"Authorization": f"Bearer {token}"}
    t1_file = tmp_path / "bpmn" / "t1" / "finance" / "invoice-approval" / LEGACY_FILE
    t2_file = tmp_path / "bpmn" / "t2" / "finance" / "invoice-approval" / LEGACY_FILE
    t1_before = t1_file.read_text(encoding="utf-8")

    for xml in (VALID_BPMN, CHANGED_BPMN):
        _put_file(client, headers, LEGACY, f"{LEGACY_FILE}?tenantId=t2", xml)
    # v1 baseline (the pre-history published file), v2 VALID, v3 CHANGED.
    t2_rows = _history(client, headers, LEGACY, tenantId="t2")["results"]
    assert [(row["version"], row["action"]) for row in t2_rows] == [(3, "save"), (2, "save"), (1, "baseline")]
    valid_version = 2

    unscoped = client.post(f"/v1.0/m8flow/process-models/{LEGACY}/versions/{valid_version}/revert", headers=headers)
    assert unscoped.status_code == 400
    assert unscoped.get_json()["error_code"] == "tenant_required"

    reverted = client.post(
        f"/v1.0/m8flow/process-models/{LEGACY}/versions/{valid_version}/revert?tenantId=t2", headers=headers
    )
    assert reverted.status_code == 200, reverted.get_json()
    assert reverted.get_json()["tenant_id"] == "t2"
    assert t2_file.read_text(encoding="utf-8") == VALID_BPMN
    assert t1_file.read_text(encoding="utf-8") == t1_before
    assert _history(client, headers, LEGACY, tenantId="t1")["results"] == []
