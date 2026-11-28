from __future__ import annotations

import socket
import threading
import time
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
import uvicorn

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, import_yaml, sync_groups
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

MINIMAL_BPMN = b"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_1" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1"/>
  </bpmn:process>
</bpmn:definitions>
"""
POC_BPMN = Path(__file__).resolve().parents[3] / "fixtures" / "invoice_approval_poc.bpmn"


def _login_user(client, db_session, *, username: str, groups: list[str], tenant_id: str):
    from m8flow_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id, name=tenant_id)
    user = ensure_user(
        db_session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=username,
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user, token


def _headers(token: str, **extra) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _create_template(client, token, *, name: str, published: bool = False, bpmn: bytes = MINIMAL_BPMN):
    key = name.lower().replace(" ", "-")
    response = client.post(
        "/v1.0/m8flow/templates",
        files={"files": ("diagram.bpmn", bpmn, "application/xml")},
        headers=_headers(
            token,
            **{
                "X-Template-Key": key,
                "X-Template-Name": name,
                "X-Template-Visibility": "TENANT",
                "X-Template-Is-Published": "true" if published else "false",
            },
        ),
    )
    return response


@pytest.mark.parametrize("content_type", ["application/xml", "application/xml; charset=utf-8"])
def test_template_create_accepts_legacy_raw_xml_with_deprecation_headers(
    client, db_session, app, tmp_path, monkeypatch, content_type
):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = str(tmp_path / "templates")
    _admin, token = _login_user(
        client, db_session, username="tenant-admin", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/templates",
        data=MINIMAL_BPMN,
        content_type=content_type,
        headers=_headers(token, **{"X-Template-Key": "raw-xml", "X-Template-Name": "Raw XML"}),
    )
    assert response.status_code == 201, response.text
    assert response.get_json()["templateKey"] == "raw-xml"
    assert response.headers["Deprecation"] == "true"
    assert "multipart/form-data" in response.headers["Warning"]


def test_template_create_rejects_other_media_types_and_documents_legacy_xml(client, db_session):
    _admin, token = _login_user(
        client, db_session, username="tenant-admin", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    response = client.post(
        "/v1.0/m8flow/templates",
        data=b"{}",
        content_type="application/json",
        headers=_headers(token, **{"X-Template-Key": "unsupported", "X-Template-Name": "Unsupported"}),
    )

    assert response.status_code == 415, response.text
    assert "multipart/form-data" in response.get_json()["message"]
    # Connexion rejects unsupported content types before the route runs. Its
    # generated error still lists application/xml as an accepted legacy type.
    assert "application/xml" in response.get_json()["message"]


@pytest.mark.parametrize(
    "content_type",
    ["application/xml;something-invalid", "application/xml; charset="],
)
def test_template_create_rejects_malformed_legacy_xml_content_type(
    client, db_session, app, tmp_path, monkeypatch, content_type
):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = str(tmp_path / "templates")
    _admin, token = _login_user(
        client,
        db_session,
        username="tenant-admin-malformed-type",
        groups=["t1:tenant-admin"],
        tenant_id="t1",
    )
    response = client.post(
        "/v1.0/m8flow/templates",
        data=MINIMAL_BPMN,
        content_type=content_type,
        headers=_headers(
            token,
            **{"X-Template-Key": "malformed-type", "X-Template-Name": "Malformed Type"},
        ),
    )

    assert response.status_code == 415, response.text
    assert "multipart/form-data" in response.get_json()["message"]
    assert "application/xml" in response.get_json()["message"]


def test_template_create_rejects_missing_content_type(client, db_session):
    _admin, token = _login_user(
        client,
        db_session,
        username="tenant-admin-missing-type",
        groups=["t1:tenant-admin"],
        tenant_id="t1",
    )
    response = client.post(
        "/v1.0/m8flow/templates",
        data=MINIMAL_BPMN,
        headers=_headers(
            token,
            **{
                "Content-Type": "",
                "X-Template-Key": "missing-type",
                "X-Template-Name": "Missing Type",
            },
        ),
    )

    assert response.status_code == 415, response.text
    assert "multipart/form-data" in response.get_json()["message"]
    assert "application/xml" in response.get_json()["message"]


def test_template_create_accepts_charset_xml_over_live_http(
    client, db_session, app, connexion_app, tmp_path, monkeypatch
):
    """Exercise charset-qualified legacy XML over TCP through Uvicorn + Connexion."""
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = str(tmp_path / "templates")
    _admin, token = _login_user(
        client,
        db_session,
        username="tenant-admin-http",
        groups=["t1:tenant-admin"],
        tenant_id="t1",
    )

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(connexion_app, log_level="error", lifespan="off"))
    server_thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    server_thread.start()

    try:
        deadline = time.monotonic() + 5
        while not server.started and server_thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Uvicorn did not start before timeout"

        response = httpx.post(
            f"http://127.0.0.1:{port}/v1.0/m8flow/templates",
            content=MINIMAL_BPMN,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/xml; charset=utf-8",
                "Cookie": f"{SELECTED_TENANT_COOKIE_NAME}=t1",
                "X-Template-Key": "raw-xml-http",
                "X-Template-Name": "Raw XML over HTTP",
            },
            timeout=5,
        )
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)
        listener.close()

    assert not server_thread.is_alive(), "Uvicorn did not stop cleanly"
    assert response.status_code == 201, response.text
    assert response.json()["templateKey"] == "raw-xml-http"
    assert response.headers["Deprecation"] == "true"
    assert "multipart/form-data" in response.headers["Warning"]


def test_list_create_publish_file_fork_restore_and_provenance(client, db_session, app, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = str(tmp_path / "templates")
    (tmp_path / "bpmn" / "t1" / "finance").mkdir(parents=True)

    _admin, admin_token = _login_user(
        client, db_session, username="tenant-admin", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    admin_headers = _headers(admin_token)

    created = _create_template(client, admin_token, name="Invoice Flow")
    assert created.status_code == 201, created.text
    draft = created.get_json()
    assert draft["isPublished"] is False
    assert draft["templateKey"] == "invoice-flow"
    template_id = draft["id"]

    listed = client.get("/v1.0/m8flow/templates?latest_only=true&search=Invoice", headers=admin_headers)
    assert listed.status_code == 200
    # Contract (api.yml TemplateListResponse): an object with results + pagination, not a bare array.
    assert listed.get_json()["pagination"] == {"count": 1, "total": 1, "pages": 1}
    results = listed.get_json()["results"]
    assert [row["id"] for row in results] == [template_id]
    assert results[0]["visibility"] == "TENANT"

    published = client.put(
        f"/v1.0/m8flow/templates/{template_id}",
        json={"is_published": True},
        headers=admin_headers,
    )
    assert published.status_code == 200, published.text
    assert published.get_json()["isPublished"] is True

    forked = client.put(
        f"/v1.0/m8flow/templates/{template_id}/files/diagram.bpmn",
        data=MINIMAL_BPMN.replace(b"Process_1", b"Process_draft"),
        content_type="application/xml",
        headers=admin_headers,
    )
    assert forked.status_code == 200, forked.text
    draft_version = forked.get_json()
    assert draft_version["id"] != template_id
    assert draft_version["isPublished"] is False
    assert draft_version["version"] == "V2"

    unpublished = _create_template(client, admin_token, name="Draft Only")
    assert unpublished.status_code == 201
    unpublished_id = unpublished.get_json()["id"]
    denied_create = client.post(
        f"/v1.0/m8flow/templates/{unpublished_id}/create-process-model",
        json={"process_group_id": "finance", "display_name": "From Draft"},
        headers=admin_headers,
    )
    assert denied_create.status_code == 400
    assert denied_create.get_json()["error_code"] == "invalid_template_state"

    poc = POC_BPMN.read_bytes()
    published_source = _create_template(client, admin_token, name="Poc Source", published=True, bpmn=poc)
    assert published_source.status_code == 201, published_source.text
    source_id = published_source.get_json()["id"]
    created_pm = client.post(
        f"/v1.0/m8flow/templates/{source_id}/create-process-model",
        json={
            "process_group_id": "finance",
            "display_name": "From Template",
            "process_model_id": "from-template",
        },
        headers=admin_headers,
    )
    assert created_pm.status_code == 201, created_pm.text
    info = created_pm.get_json()["template_info"]
    assert info["source_template_id"] == source_id
    assert info["source_template_key"] == "poc-source"
    assert info["process_model_identifier"] == "finance/from-template"

    deleted = client.delete(f"/v1.0/m8flow/templates/{source_id}", headers=admin_headers)
    assert deleted.status_code == 200
    gone = client.get("/v1.0/m8flow/templates", headers=admin_headers)
    assert all(row["id"] != source_id for row in gone.get_json()["results"])
    deleted_only = client.get("/v1.0/m8flow/templates?deleted_only=true", headers=admin_headers)
    assert source_id in {row["id"] for row in deleted_only.get_json()["results"]}

    restored = client.post(f"/v1.0/m8flow/templates/{source_id}/restore", headers=admin_headers)
    assert restored.status_code == 200, restored.text
    assert restored.get_json()["isDeleted"] is False

    editor, editor_token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    editor_headers = _headers(editor_token)
    assert client.get("/v1.0/onboarding", headers=editor_headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=editor_headers).status_code == 200
    assert editor.username == "editor"


def test_super_admin_cannot_write_templates(client, db_session):
    _user, token = _login_user(
        client, db_session, username="root", groups=["super-admin"], tenant_id="t1"
    )
    created = _create_template(client, token, name="Admin Write")
    assert created.status_code == 403
    assert "read-only" in created.get_json()["message"].lower() or created.get_json()["error_code"] == "forbidden"


def test_collaboration_template_publishes_independent_models_and_form_only_releases(
    client, db_session, app, tmp_path, monkeypatch
):
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import human_task
    from m8flow_backend.catalog import versions
    from m8flow_backend.models.process_model_version import ProcessModelState

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = str(tmp_path / "templates")
    (tmp_path / "bpmn" / "t1" / "finance").mkdir(parents=True)
    bpmn_name = "orders.bpmn"
    source = POC_BPMN.with_name("order-fulfilment-collaboration.bpmn").read_bytes()
    source = source.replace(b'processRef="orders:Order"', b'processRef="Order"').replace(
        b'xmlns:orders=',
        b'xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core" xmlns:orders=',
        1,
    ).replace(
        b'<bpmn:userTask id="ApproveOrder" name="Approve order"/>',
        b'<bpmn:userTask id="ApproveOrder" name="Approve order"><bpmn:extensionElements>'
        b'<spiffworkflow:properties>'
        b'<spiffworkflow:property name="formJsonSchemaFilename" value="approve_order-schema.json"/>'
        b'<spiffworkflow:property name="formUiSchemaFilename" value="approve_order-uischema.json"/>'
        b'</spiffworkflow:properties></bpmn:extensionElements></bpmn:userTask>',
    )
    files = {
        bpmn_name: source,
        "approve_order-schema.json": b'{"title": "Approve order", "type": "object", "properties": {}}',
        "approve_order-uischema.json": b'{"type": "VerticalLayout", "elements": []}',
    }
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w") as package:
        for name, content in files.items():
            package.writestr(name, content)
    archive = archive_buffer.getvalue()
    _admin, token = _login_user(
        client, db_session, username="template-admin", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    imported = client.post(
        "/v1.0/m8flow/templates/import",
        data=archive,
        content_type="application/zip",
        headers=_headers(token, **{"X-Template-Key": "collaboration", "X-Template-Name": "Collaboration"}),
    )
    assert imported.status_code == 201, imported.json
    template_id = imported.json["id"]
    assert imported.json["isPublished"] is False
    published_template = client.put(
        f"/v1.0/m8flow/templates/{template_id}", json={"is_published": True}, headers=_headers(token)
    )
    assert published_template.status_code == 200, published_template.json
    assert client.get(
        f"/v1.0/m8flow/templates/{template_id}/files/{bpmn_name}", headers=_headers(token),
    ).data == files[bpmn_name]

    _editor, token = _login_user(
        client, db_session, username="collaboration-editor", groups=["t1:editor"], tenant_id="t1"
    )
    headers = _headers(token)
    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200

    def revision(response):
        return {**headers, "If-Match": '"' + response.json["working_revision"] + '"'}

    sources, participants = {}, {}

    def start(path, key="shared-order"):
        response = client.post(
            f"{path}/start", headers=headers,
            json={"bpmn_process_id": participants[path], "collaboration_correlation_key": key},
        )
        assert response.status_code == 201, response.json
        db_session.expire_all()
        instance = db_session.get(ProcessInstanceModel, response.json["id"])
        assert instance.status == "user_input_required"
        assert instance.bpmn_process_definition.source_bpmn_xml == sources[path].decode()
        return instance

    paths, published_models, instances = [], [], []
    for model_id in ("orders", "orders-copy"):
        created = client.post(
            f"/v1.0/m8flow/templates/{template_id}/create-process-model", headers=headers,
            json={"process_group_id": "finance", "display_name": model_id, "process_model_id": model_id},
        )
        assert created.status_code == 201, created.json
        path = f"/v1.0/m8flow/process-models/finance:{model_id}"
        detail = client.get(path, headers=headers)
        assert detail.status_code == 200, detail.json
        sources[path] = client.get(f"{path}/files/{bpmn_name}", headers=headers).data
        published = client.post(f"{path}/publish", headers=revision(detail))
        assert published.status_code == 200, published.json
        assert published.json["published_version"] == 1
        detail = client.get(path, headers=headers)
        pools = detail.json["collaboration_participants"]
        assert [pool["name"] for pool in pools] == ["Order", "Fulfilment"]
        participants[path] = pools[0]["id"]
        assert client.get(f"{path}/files/{bpmn_name}", headers=headers).data == sources[path]
        paths.append(path)
        published_models.append(published)
        instances.append(start(path))
    original, copied = instances
    assert original.bpmn_process_definition_id != copied.bpmn_process_definition_id
    assert copied.bpmn_process_definition.process_model_identifier == "finance/orders-copy"
    original_definition_id = original.bpmn_process_definition_id

    path = paths[0]
    repeated = client.post(f"{path}/publish", headers=revision(published_models[0]))
    assert repeated.status_code == 200, repeated.json
    assert repeated.json["published_version"] == 1
    changed_schema = files["approve_order-schema.json"].replace(b'"Approve order"', b'"Updated approval"')
    saved = client.put(
        f"{path}/files/approve_order-schema.json", headers=revision(repeated),
        content_type="application/octet-stream", data=changed_schema,
    )
    assert saved.status_code == 200, saved.json
    assert saved.json["draft_version"] == 2
    assert start(path, "before-publish").bpmn_process_definition_id == original_definition_id
    second = client.post(f"{path}/publish", headers=revision(saved))
    assert second.status_code == 200, second.json
    assert second.json["published_version"] == 2
    latest = start(path)
    assert latest.bpmn_process_definition_id != original_definition_id
    assert latest.bpmn_version_control_identifier.endswith(":2")
    assert original.bpmn_version_control_identifier.endswith(":1")
    assert original.bpmn_process_definition.source_bpmn_xml == sources[path].decode()
    assert copied.bpmn_version_control_identifier.endswith(":1")

    def form_title(instance):
        return human_task.form_schema_for_task(
            db_session, tenant_id="t1", work_item=instance.work_items[0],
        )["schema"]["title"]

    assert form_title(original) == form_title(copied) == "Approve order"
    assert form_title(latest) == "Updated approval"
    model = db_session.get(ProcessModelState, ("t1", "finance/orders"))
    for number in (1, 2):
        release = versions.release(db_session, model, number)
        assert versions.read_file(release.contents, bpmn_name) == sources[path]


def test_super_admin_can_create_process_model_from_published_template(
    client, db_session, app, tmp_path, monkeypatch
):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = str(tmp_path / "templates")
    (tmp_path / "bpmn" / "t1" / "finance").mkdir(parents=True)
    (tmp_path / "bpmn" / "t1" / "finance" / "process_group.json").write_text(
        '{"display_name": "Finance"}',
        encoding="utf-8",
    )

    _admin, admin_token = _login_user(
        client, db_session, username="tenant-admin-sa-tpl", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    published = _create_template(client, admin_token, name="Sa Source", published=True)
    assert published.status_code == 201, published.text
    source_id = published.get_json()["id"]

    _sa, sa_token = _login_user(
        client, db_session, username="root-from-tpl", groups=["super-admin"], tenant_id="t1"
    )
    created_pm = client.post(
        f"/v1.0/m8flow/templates/{source_id}/create-process-model?tenantId=t1",
        json={
            "process_group_id": "finance",
            "display_name": "From Template SA",
            "process_model_id": "from-template-sa",
            "m8f_tenant_id": "t1",
        },
        headers=_headers(sa_token),
    )
    assert created_pm.status_code == 201, created_pm.text
    info = created_pm.get_json()["template_info"]
    assert info["source_template_id"] == source_id
    assert info["process_model_identifier"] == "finance/from-template-sa"
    assert created_pm.json["process_model"]["draft_version"] == 1
    model = client.get(
        "/v1.0/m8flow/process-models/finance:from-template-sa?tenantId=t1", headers=_headers(sa_token),
    )
    assert model.status_code == 200
    assert [entry["name"] for entry in model.json["files"]] == ["diagram.bpmn"]

    client.delete_cookie(SELECTED_TENANT_COOKIE_NAME)
    missing_tenant = client.post(
        f"/v1.0/m8flow/templates/{source_id}/create-process-model",
        json={
            "process_group_id": "finance",
            "display_name": "No Tenant",
            "process_model_id": "no-tenant",
        },
        headers=_headers(sa_token),
    )
    assert missing_tenant.status_code == 400
    assert missing_tenant.get_json()["error_code"] == "tenant_required"


def test_create_process_model_with_template_file_missing_from_storage(
    client, db_session, app, tmp_path, monkeypatch
):
    """M8F-650: a template file missing from storage fails with an actionable
    message and leaves nothing on disk, so a retry with the same id works."""
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = str(tmp_path / "templates")
    (tmp_path / "bpmn" / "t1" / "finance").mkdir(parents=True)

    _admin, admin_token = _login_user(
        client, db_session, username="tenant-admin-missing", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    published = _create_template(client, admin_token, name="Missing File Source", published=True)
    assert published.status_code == 201, published.text
    source_id = published.get_json()["id"]
    stored = next((tmp_path / "templates").rglob("diagram.bpmn"))
    stored_bytes = stored.read_bytes()
    stored.unlink()

    body = {"process_group_id": "finance", "display_name": "Missing", "process_model_id": "missing"}
    url = f"/v1.0/m8flow/templates/{source_id}/create-process-model"
    failed = client.post(url, json=body, headers=_headers(admin_token))
    assert failed.status_code == 500
    error = failed.get_json()
    assert error["error_code"] == "file_copy_failed"
    assert "diagram.bpmn" in error["message"]
    assert "re-import" in error["message"].lower()
    assert not (tmp_path / "bpmn" / "t1" / "finance" / "missing").exists()

    stored.write_bytes(stored_bytes)
    retried = client.post(url, json=body, headers=_headers(admin_token))
    assert retried.status_code == 201, retried.text


def test_reuses_deleted_legacy_model_id_from_template(client, db_session, app, tmp_path, monkeypatch):
    from sqlalchemy import select

    from m8flow_backend.catalog import versions
    from m8flow_backend.models.process_model_template import ProcessModelTemplateModel

    root = tmp_path / "bpmn"
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(root))
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = str(tmp_path / "templates")
    model_id = "finance/reused"
    folder = root / "t1" / model_id
    folder.mkdir(parents=True)
    legacy_file = folder / "legacy.bpmn"
    legacy_file.write_bytes(MINIMAL_BPMN)
    occupied = root / "t1" / "finance" / "occupied"
    occupied.mkdir()
    (occupied / "process_group.json").write_text("{}", encoding="utf-8")
    user, token = _login_user(
        client, db_session, username="template-recreator", groups=["t1:tenant-admin"], tenant_id="t1",
    )
    old_template = _create_template(client, token, name="Original", published=True)
    new_template = _create_template(client, token, name="Replacement", published=True)
    assert old_template.status_code == new_template.status_code == 201
    old_info = old_template.json
    new_id = new_template.json["id"]
    model = versions.import_legacy(db_session, "t1", model_id)
    old_generation, old_revision = model.generation, model.working_revision
    db_session.add(ProcessModelTemplateModel(
        m8f_tenant_id="t1", process_model_identifier=model_id, created_by=user.username,
        source_template_id=old_info["id"], source_template_key=old_info["templateKey"],
        source_template_version=old_info["version"], source_template_name="Original",
    ))
    db_session.commit()

    def create_target(leaf):
        return client.post(
            f"/v1.0/m8flow/templates/{new_id}/create-process-model", headers=_headers(token),
            json={"process_group_id": "finance", "process_model_id": leaf, "display_name": "Replacement"},
        )

    live = create_target("reused")
    assert (live.status_code, live.json["error_code"]) == (409, "process_model_exists")
    collision = create_target("occupied")
    assert (collision.status_code, collision.json["error_code"]) == (409, "process_group_exists")
    assert client.delete("/v1.0/m8flow/process-models/finance:reused", headers=_headers(token)).status_code == 200
    assert legacy_file.read_bytes() == MINIMAL_BPMN

    recreated = create_target("reused")
    assert recreated.status_code == 201, recreated.json
    assert recreated.json["process_model"]["draft_version"] == 1
    assert recreated.json["process_model"]["published_version"] is None
    assert recreated.json["template_info"]["source_template_id"] == new_id
    model = versions.write_state(db_session, "t1", model_id)
    assert model.generation != old_generation
    assert model.working_revision != old_revision
    assert set(model.working["files"]) == {"diagram.bpmn"}
    provenance_query = select(ProcessModelTemplateModel).filter_by(
        m8f_tenant_id="t1", process_model_identifier=model_id,
    )
    provenance, = db_session.scalars(provenance_query)
    assert provenance.source_template_id == new_id
    assert versions.release_by_reference(db_session, "t1", model_id, f"{old_generation}:1") is not None

    assert client.delete("/v1.0/m8flow/process-models/finance:reused", headers=_headers(token)).status_code == 200
    plain = client.post(
        "/v1.0/m8flow/process-models", headers=_headers(token), json={"group_id": "finance", "id": "reused"},
    )
    assert plain.status_code == 201, plain.json
    assert db_session.scalars(provenance_query).all() == []


def test_template_headers_decode_percent_encoded_non_ascii():
    from flask import Flask, request

    from m8flow_backend.routes.templates_controller import _metadata_from_headers

    headers = {
        "X-Template-Header-Encoding": "percent",
        "X-Template-Key": "cafe",
        "X-Template-Name": "Caf%C3%A9%20flow",
        "X-Template-Description": "Aprobaci%C3%B3n%20%E2%80%94%20%E2%9C%93",
    }
    with Flask(__name__).test_request_context(headers=headers):
        assert request.headers["X-Template-Name"] == "Caf%C3%A9%20flow"
        metadata = _metadata_from_headers()
    assert metadata["name"] == "Café flow"
    assert metadata["description"] == "Aprobación — ✓"
    assert metadata["visibility"] == "PRIVATE"


def test_template_headers_are_literal_without_encoding_marker():
    from flask import Flask

    from m8flow_backend.routes.templates_controller import _metadata_from_headers

    with Flask(__name__).test_request_context(headers={"X-Template-Name": "100%25 done"}):
        assert _metadata_from_headers()["name"] == "100%25 done"
