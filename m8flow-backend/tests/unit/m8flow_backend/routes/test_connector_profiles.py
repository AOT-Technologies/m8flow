from __future__ import annotations

import json

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.connectors.service import secret_ref
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, import_yaml, sync_groups
from m8flow_backend.models.native import SecretModel
from m8flow_backend.secrets import get_secret_value
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

_PROFILES = "/v1.0/m8flow/connector-profiles"
_TEMPLATES = "/v1.0/m8flow/connector-templates"


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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _http_profile_body(**overrides):
    body = {
        "connector_type": "http",
        "profile_name": "default",
        "display_name": "Default HTTP",
        "config": {
            "basic_auth_username": "api-user",
            "basic_auth_password": "super-secret",
        },
    }
    body.update(overrides)
    return body


def _assert_no_secret_leak(payload, *, password: str = "super-secret") -> None:
    assert password not in json.dumps(payload)
    if isinstance(payload, list):
        for item in payload:
            _assert_no_secret_leak(item, password=password)
        return
    if isinstance(payload, dict):
        assert "value" not in payload
        assert "secret_refs" not in payload
        assert payload.get("config", {}) == {}


def test_http_template_is_basic_auth_on_profile_and_url_on_task(client, db_session):
    _user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    listed = client.get(_TEMPLATES, headers=_headers(token))
    assert listed.status_code == 200
    templates = listed.get_json()
    assert [item["id"] for item in templates] == ["http"]
    http = templates[0]
    assert http["supportsProfiles"] is True
    assert {field["id"] for field in http["profileFields"]} == {
        "basic_auth_username",
        "basic_auth_password",
    }
    assert {field["id"] for field in http["taskFields"]} == {"url", "headers", "params", "data"}

    shown = client.get(f"{_TEMPLATES}/http", headers=_headers(token))
    assert shown.status_code == 200
    assert shown.get_json()["id"] == "http"

    missing = client.get(f"{_TEMPLATES}/smtp", headers=_headers(token))
    assert missing.status_code == 404


def test_integrator_crud_never_returns_secret_values(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)

    created = client.post(_PROFILES, json=_http_profile_body(), headers=headers)
    assert created.status_code == 201
    body = created.get_json()
    assert body["profile_name"] == "default"
    assert body["connector_type"] == "http"
    assert body["is_active"] is True
    assert body["configured_secrets"] == ["basic_auth_password", "basic_auth_username"]
    _assert_no_secret_leak(body)
    profile_id = body["id"]

    db_session.expire_all()
    stored = db_session.query(SecretModel).filter_by(
        m8f_tenant_id="t1", key=secret_ref(profile_id, "basic_auth_password")
    ).one()
    assert stored.value != "super-secret"
    assert get_secret_value(db_session, tenant_id="t1", key=secret_ref(profile_id, "basic_auth_password")) == (
        "super-secret"
    )

    listed = client.get(_PROFILES, headers=headers)
    assert listed.status_code == 200
    payload = listed.get_json()
    assert len(payload) == 1
    _assert_no_secret_leak(payload)

    shown = client.get(f"{_PROFILES}/{profile_id}", headers=headers)
    assert shown.status_code == 200
    _assert_no_secret_leak(shown.get_json())

    updated = client.put(
        f"{_PROFILES}/{profile_id}",
        json={"display_name": "Prod HTTP", "config": {"basic_auth_password": ""}},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.get_json()["display_name"] == "Prod HTTP"
    _assert_no_secret_leak(updated.get_json())
    assert get_secret_value(
        db_session, tenant_id="t1", key=secret_ref(profile_id, "basic_auth_password")
    ) == "super-secret"

    duplicate = client.post(_PROFILES, json=_http_profile_body(), headers=headers)
    assert duplicate.status_code == 409

    deactivated = client.delete(f"{_PROFILES}/{profile_id}", headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.get_json()["is_active"] is False

    active_only = client.get(
        _PROFILES, headers=headers, query_string={"include_inactive": "false"}
    )
    assert active_only.status_code == 200
    assert active_only.get_json() == []

    with_inactive = client.get(_PROFILES, headers=headers)
    assert with_inactive.get_json()[0]["is_active"] is False

    removed = client.delete(
        f"{_PROFILES}/{profile_id}", headers=headers, query_string={"hard": "true"}
    )
    assert removed.status_code == 200
    assert removed.get_json() == {"ok": True}
    after = client.get(_PROFILES, headers=headers)
    assert after.get_json() == []
    db_session.expire_all()
    assert db_session.query(SecretModel).filter_by(m8f_tenant_id="t1").count() == 0


def test_editor_can_read_and_cannot_write_profiles(client, db_session):
    _integrator, integrator_token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    created = client.post(
        _PROFILES, json=_http_profile_body(), headers=_headers(integrator_token)
    )
    assert created.status_code == 201
    profile_id = created.get_json()["id"]

    _editor, editor_token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    headers = _headers(editor_token)

    listed = client.get(_PROFILES, headers=headers)
    assert listed.status_code == 200
    rows = listed.get_json()
    assert [row["profile_name"] for row in rows] == ["default"]
    _assert_no_secret_leak(rows)

    shown = client.get(f"{_PROFILES}/{profile_id}", headers=headers)
    assert shown.status_code == 200

    denied_create = client.post(
        _PROFILES, json=_http_profile_body(profile_name="other"), headers=headers
    )
    assert denied_create.status_code == 403
    denied_update = client.put(
        f"{_PROFILES}/{profile_id}", json={"display_name": "Nope"}, headers=headers
    )
    assert denied_update.status_code == 403
    denied_delete = client.delete(f"{_PROFILES}/{profile_id}", headers=headers)
    assert denied_delete.status_code == 403


def test_viewer_and_reviewer_can_read_profile_names(client, db_session):
    _integrator, integrator_token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    client.post(_PROFILES, json=_http_profile_body(), headers=_headers(integrator_token))

    for role in ("viewer", "reviewer"):
        _user, token = _login_user(
            client, db_session, username=role, groups=[f"t1:{role}"], tenant_id="t1"
        )
        listed = client.get(_PROFILES, headers=_headers(token))
        assert listed.status_code == 200
        _assert_no_secret_leak(listed.get_json())
        created = client.post(
            _PROFILES, json=_http_profile_body(profile_name="nope"), headers=_headers(token)
        )
        assert created.status_code == 403


def test_profiles_are_isolated_across_tenants(client, db_session):
    _user_a, token_a = _login_user(
        client, db_session, username="integrator-a", groups=["t1:integrator"], tenant_id="t1"
    )
    created = client.post(_PROFILES, json=_http_profile_body(), headers=_headers(token_a))
    assert created.status_code == 201
    profile_id = created.get_json()["id"]

    _user_b, token_b = _login_user(
        client, db_session, username="integrator-b", groups=["t2:integrator"], tenant_id="t2"
    )
    listed_b = client.get(_PROFILES, headers=_headers(token_b))
    assert listed_b.get_json() == []
    shown_b = client.get(f"{_PROFILES}/{profile_id}", headers=_headers(token_b))
    assert shown_b.status_code == 404


def test_grouped_catalog_marks_http_supports_profiles(client, db_session, monkeypatch):
    class _Param:
        name = "url"
        parameter_type = "string"

    class _Command:
        operation_id = "http/GetRequestV2"
        parameters = [_Param()]

    class _Registry:
        def list_commands(self):
            return [_Command()]

    monkeypatch.setattr(
        "m8flow_backend.secrets.build_host_service_task_registry",
        lambda: _Registry(),
    )
    _user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    response = client.get(
        "/v1.0/m8flow/connectors-grouped", headers=_headers(token)
    )
    assert response.status_code == 200
    groups = response.get_json()
    http = next(group for group in groups if group["id"] == "http")
    assert http["supportsProfiles"] is True
    assert "configFields" not in http
