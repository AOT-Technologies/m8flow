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
        # Only non-credential fields are ever read back (detail endpoint).
        assert set(payload.get("config", {})) <= {"basic_auth_username"}


def test_http_template_is_basic_auth_on_profile_and_url_on_task(client, db_session):
    _user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    listed = client.get(_TEMPLATES, headers=_headers(token))
    assert listed.status_code == 200
    templates = listed.get_json()
    by_id = {item["id"]: item for item in templates}
    # http plus the m8flow connector families the proxy serves.
    assert "http" in by_id
    http = by_id["http"]
    assert http["supportsProfiles"] is True
    assert {field["id"] for field in http["profileFields"]} == {
        "basic_auth_username",
        "basic_auth_password",
    }
    assert {field["id"] for field in http["taskFields"]} == {"url", "headers", "params", "data"}

    shown = client.get(f"{_TEMPLATES}/http", headers=_headers(token))
    assert shown.status_code == 200
    assert shown.get_json()["id"] == "http"

    # smtp is a registered family; its credentials live on the profile and the
    # message itself on the task.
    smtp = client.get(f"{_TEMPLATES}/smtp", headers=_headers(token))
    assert smtp.status_code == 200
    smtp_body = smtp.get_json()
    assert "smtp_host" in {field["id"] for field in smtp_body["profileFields"]}
    assert "email_to" in {field["id"] for field in smtp_body["taskFields"]}

    missing = client.get(f"{_TEMPLATES}/not_a_connector", headers=_headers(token))
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


def _smtp_profile_body(**overrides):
    body = {
        "connector_type": "smtp",
        "profile_name": "mail",
        "display_name": "Mail",
        "config": {
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "email_from": "noreply@example.com",
            "smtp_password": "super-secret",
        },
    }
    body.update(overrides)
    return body


def test_detail_prefills_plain_fields_but_never_credentials(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    created = client.post(_PROFILES, json=_smtp_profile_body(), headers=headers)
    assert created.status_code == 201
    profile_id = created.get_json()["id"]

    shown = client.get(f"{_PROFILES}/{profile_id}", headers=headers).get_json()
    assert shown["config"] == {
        "smtp_host": "smtp.example.com",
        "smtp_port": "587",
        "email_from": "noreply@example.com",
    }
    assert "smtp_password" in shown["configured_secrets"]
    assert "super-secret" not in json.dumps(shown)

    # The list stays metadata-only: no per-row decrypts.
    listed = client.get(_PROFILES, headers=headers).get_json()
    assert listed[0]["config"] == {}
    assert listed[0]["updated_at"]


def test_update_clears_optional_fields_and_keeps_blank_ones(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    profile_id = client.post(_PROFILES, json=_smtp_profile_body(), headers=headers).get_json()["id"]
    path = f"{_PROFILES}/{profile_id}"

    cleared = client.put(
        path,
        json={"config": {"smtp_host": "", "smtp_port": "465"}, "clear": ["email_from", "smtp_password"]},
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.get_json()["configured_secrets"] == ["smtp_host", "smtp_port"]
    db_session.expire_all()
    assert get_secret_value(db_session, tenant_id="t1", key=secret_ref(profile_id, "smtp_password")) is None
    assert get_secret_value(db_session, tenant_id="t1", key=secret_ref(profile_id, "email_from")) is None
    shown = client.get(path, headers=headers).get_json()
    # Blank host kept its value; port was replaced.
    assert shown["config"] == {"smtp_host": "smtp.example.com", "smtp_port": "465"}

    required = client.put(path, json={"clear": ["smtp_host"]}, headers=headers)
    assert required.status_code == 400
    assert "Required fields cannot be cleared" in json.dumps(required.get_json())

    unknown = client.put(path, json={"clear": ["nope"]}, headers=headers)
    assert unknown.status_code == 400

    both = client.put(
        path, json={"config": {"email_from": "a@example.com"}, "clear": ["email_from"]}, headers=headers
    )
    assert both.status_code == 400

    not_a_list = client.put(path, json={"clear": "email_from"}, headers=headers)
    assert not_a_list.status_code == 400


def test_update_tolerates_duplicate_clear_entries(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    profile_id = client.post(_PROFILES, json=_smtp_profile_body(), headers=headers).get_json()["id"]

    cleared = client.put(
        f"{_PROFILES}/{profile_id}",
        json={"clear": ["smtp_password", "smtp_password"]},
        headers=headers,
    )
    assert cleared.status_code == 200
    assert "smtp_password" not in cleared.get_json()["configured_secrets"]
    db_session.expire_all()
    assert get_secret_value(db_session, tenant_id="t1", key=secret_ref(profile_id, "smtp_password")) is None


def test_create_rejects_invalid_names_with_field_errors(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)

    cases = [
        ({"display_name": "@#%$%%a$#%^&**gf"}, "display_name", "Must start with a letter or number"),
        ({"display_name": "!!!"}, "display_name", "Must start with a letter or number"),
        ({"display_name": "   "}, "display_name", "required"),
        ({"display_name": "ab"}, "display_name", "3–60 characters"),
        ({"display_name": "a" * 61}, "display_name", "3–60 characters"),
        ({"display_name": "Prod <script>"}, "display_name", "Use letters, numbers"),
        ({"profile_name": "ab"}, "profile_name", "3–50 characters"),
        ({"profile_name": "a" * 51}, "profile_name", "3–50 characters"),
        ({"profile_name": "Prod_HTTP"}, "profile_name", "lowercase letters"),
        ({"profile_name": "prod--http"}, "profile_name", "single hyphens"),
        ({"profile_name": "-prod"}, "profile_name", "lowercase letters"),
    ]
    for overrides, field, fragment in cases:
        response = client.post(_PROFILES, json=_http_profile_body(**overrides), headers=headers)
        assert response.status_code == 400, overrides
        body = response.get_json()
        assert body["error_code"] == "validation_error"
        assert fragment in body["field_errors"][field], (overrides, body)
    assert client.get(_PROFILES, headers=headers).get_json() == []

    ok = client.post(
        _PROFILES,
        json=_http_profile_body(display_name="GitHub Prod (Org A)", profile_name="github-prod"),
        headers=headers,
    )
    assert ok.status_code == 201

    duplicate = client.post(
        _PROFILES,
        json=_http_profile_body(display_name="Another", profile_name="github-prod"),
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.get_json()["field_errors"]["profile_name"]


def test_update_validates_display_name_but_loads_legacy_profiles(client, db_session):
    from m8flow_backend.connectors.configuration import ConnectorConfigurationModel

    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    # A profile saved before these rules: odd name and short identifier.
    legacy = ConnectorConfigurationModel(
        m8f_tenant_id="t1",
        connector_type="http",
        profile_name="a",
        display_name="@#%$",
        config_json={},
        secret_refs={},
        is_active=True,
    )
    db_session.add(legacy)
    db_session.commit()
    path = f"{_PROFILES}/{legacy.id}"

    assert client.get(path, headers=headers).status_code == 200
    # Changes that leave the name alone still work.
    assert client.put(path, json={"is_active": False}, headers=headers).status_code == 200

    bad = client.put(path, json={"display_name": "@#%$"}, headers=headers)
    assert bad.status_code == 400
    assert "display_name" in bad.get_json()["field_errors"]

    renamed = client.put(path, json={"display_name": "Legacy HTTP"}, headers=headers)
    assert renamed.status_code == 200
    assert renamed.get_json()["profile_name"] == "a"


def test_secret_only_update_bumps_updated_at(client, db_session):
    from datetime import UTC, datetime

    from m8flow_backend.connectors.configuration import ConnectorConfigurationModel

    # Same type the HostBase timestamp listener writes: timezone-aware UTC.
    assert ConnectorConfigurationModel.__table__.c.updated_at.type.timezone is True

    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    profile_id = client.post(_PROFILES, json=_http_profile_body(), headers=headers).get_json()["id"]
    old = datetime(2020, 1, 1, tzinfo=UTC)

    # Credential-only changes reassign secret_refs, so the HostBase
    # before_update listener stamps updated_at.
    for body in ({"config": {"basic_auth_password": "rotated"}}, {"clear": ["basic_auth_username"]}):
        profile = db_session.get(ConnectorConfigurationModel, profile_id)
        profile.updated_at = old
        db_session.commit()

        updated = client.put(f"{_PROFILES}/{profile_id}", json=body, headers=headers)
        assert updated.status_code == 200
        written = datetime.fromisoformat(updated.get_json()["updated_at"])
        assert written.utcoffset() is not None and written.utcoffset().total_seconds() == 0
        assert written > old

        db_session.expire_all()
        listed = client.get(_PROFILES, headers=headers).get_json()[0]["updated_at"]
        # SQLite drops the offset on read-back; Postgres (timestamptz) keeps it.
        assert datetime.fromisoformat(listed).replace(tzinfo=None) == written.replace(tzinfo=None)
