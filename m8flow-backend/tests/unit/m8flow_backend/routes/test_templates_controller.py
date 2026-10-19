from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

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
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

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
    assert (tmp_path / "bpmn" / "t1" / "finance" / "from-template-sa").is_dir()

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
