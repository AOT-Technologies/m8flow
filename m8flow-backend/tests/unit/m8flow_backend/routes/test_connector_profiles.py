from __future__ import annotations

import json
from datetime import datetime

import pytest

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.authorization import user_has_permission
from m8flow_backend.connectors.configuration import ConnectorConfigurationModel
from m8flow_backend.connectors import service as profile_service
from m8flow_backend.connectors.service import resolve_for_runtime, secret_ref
from m8flow_backend.connectors.templates import template_for
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
        assert "basic_auth_password" not in payload.get("config", {})


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

    assert payload[0]["config"] == {}

    shown = client.get(f"{_PROFILES}/{profile_id}", headers=headers)
    assert shown.status_code == 200
    _assert_no_secret_leak(shown.get_json())
    # The edit form prefills plain settings; the password stays hidden.
    assert shown.get_json()["config"] == {"basic_auth_username": "api-user"}

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
    # Read-only roles get field names only, never the saved settings.
    assert shown.get_json()["config"] == {}

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


def test_only_editor_show_returns_config_even_if_config_json_is_set(client, db_session):
    _integrator, integrator_token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    integrator = _headers(integrator_token)
    profile_id = client.post(_PROFILES, json=_http_profile_body(), headers=integrator).get_json()["id"]
    # Nothing writes config_json today; pin that responses ignore it if it ever does.
    db_session.get(ConnectorConfigurationModel, profile_id).config_json = {"leaked": "x"}
    db_session.commit()
    _editor, editor_token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )

    assert client.get(_PROFILES, headers=integrator).get_json()[0]["config"] == {}
    assert client.get(f"{_PROFILES}/{profile_id}", headers=_headers(editor_token)).get_json()["config"] == {}
    assert client.get(f"{_PROFILES}/{profile_id}", headers=integrator).get_json()["config"] == {
        "basic_auth_username": "api-user"
    }
    updated = client.put(f"{_PROFILES}/{profile_id}", json={"description": "d"}, headers=integrator)
    assert updated.get_json()["config"] == {}
    assert client.delete(f"{_PROFILES}/{profile_id}", headers=integrator).get_json()["config"] == {}


def test_multi_org_show_prefill_follows_the_active_tenant_role(client, db_session):
    _owner, owner_token = _login_user(
        client, db_session, username="integrator-t2", groups=["t2:integrator"], tenant_id="t2"
    )
    profile_id = client.post(_PROFILES, json=_http_profile_body(), headers=_headers(owner_token)).get_json()["id"]
    # Integrator in t1 but only a viewer in t2, with t2 selected.
    user, _ = _login_user(client, db_session, username="multi", groups=["t1:integrator"], tenant_id="t1")
    _user, token = _login_user(client, db_session, username="multi", groups=["t2:viewer"], tenant_id="t2")
    assert user.id == _user.id

    shown = client.get(f"{_PROFILES}/{profile_id}", headers=_headers(token))
    assert shown.status_code == 200
    assert shown.get_json()["config"] == {}
    denied = client.put(f"{_PROFILES}/{profile_id}", json={"description": "x"}, headers=_headers(token))
    assert denied.status_code == 403


def test_set_and_clear_survive_secrets_deleted_outside_the_profile(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    profile_id = client.post(_PROFILES, json=_http_profile_body(), headers=headers).get_json()["id"]
    # As if removed from the generic Secrets page: refs remain, values are gone.
    db_session.query(SecretModel).filter_by(m8f_tenant_id="t1").delete()
    db_session.commit()

    fixed = client.put(
        f"{_PROFILES}/{profile_id}",
        json={"config": {"basic_auth_password": "new-secret"}, "clear": ["basic_auth_username"]},
        headers=headers,
    )
    assert fixed.status_code == 200
    assert fixed.get_json()["configured_secrets"] == ["basic_auth_password"]
    assert get_secret_value(
        db_session, tenant_id="t1", key=secret_ref(profile_id, "basic_auth_password")
    ) == "new-secret"


def test_user_has_permission_keeps_group_fallback_unless_disabled(client, db_session):
    # Default matches allow_uri, so callers that don't pass the flag are
    # unchanged; only an explicit False drops the editor group fallback.
    editor, _ = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    integrator, _ = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    ungranted_uri = "/v1.0/m8flow/no-grant-for-this-path"
    assert user_has_permission(editor, "PUT", ungranted_uri, session=db_session) is True
    assert (
        user_has_permission(editor, "PUT", ungranted_uri, session=db_session, group_fallback=False)
        is False
    )

    # Connector profiles opt out of the fallback by policy, so the editor is
    # denied even with the default flag; only the explicit grant lets in.
    uri = f"{_PROFILES}/1"
    assert user_has_permission(editor, "PUT", uri, session=db_session) is False
    assert (
        user_has_permission(integrator, "PUT", uri, session=db_session, group_fallback=False)
        is True
    )


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


def test_clear_removes_optional_value_and_keeps_the_rest(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    created = client.post(_PROFILES, json=_http_profile_body(), headers=headers)
    assert created.status_code == 201
    profile_id = created.get_json()["id"]
    before = created.get_json()["updated_at"]

    cleared = client.put(
        f"{_PROFILES}/{profile_id}",
        json={"clear": ["basic_auth_username"]},
        headers=headers,
    )
    assert cleared.status_code == 200
    body = cleared.get_json()
    assert body["configured_secrets"] == ["basic_auth_password"]
    assert datetime.fromisoformat(body["updated_at"]) > datetime.fromisoformat(before)

    db_session.expire_all()
    username_key = secret_ref(profile_id, "basic_auth_username")
    assert db_session.query(SecretModel).filter_by(m8f_tenant_id="t1", key=username_key).count() == 0
    assert get_secret_value(
        db_session, tenant_id="t1", key=secret_ref(profile_id, "basic_auth_password")
    ) == "super-secret"
    shown = client.get(f"{_PROFILES}/{profile_id}", headers=headers)
    assert shown.get_json()["config"] == {}

    # Clearing an unset field again is a no-op.
    again = client.put(
        f"{_PROFILES}/{profile_id}", json={"clear": ["basic_auth_username"]}, headers=headers
    )
    assert again.status_code == 200


def test_clear_rejects_unknown_required_and_conflicting_fields(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    http_id = client.post(_PROFILES, json=_http_profile_body(), headers=headers).get_json()["id"]
    smtp = client.post(
        _PROFILES,
        json={
            "connector_type": "smtp",
            "profile_name": "mail",
            "config": {"smtp_host": "smtp.example.com", "smtp_port": "587"},
        },
        headers=headers,
    )
    assert smtp.status_code == 201
    smtp_id = smtp.get_json()["id"]

    cases = [
        (http_id, {"clear": ["nope"]}),
        (http_id, {"clear": "basic_auth_username"}),
        (http_id, {"clear": [{"id": "basic_auth_username"}]}),
        (http_id, {"clear": ["basic_auth_username", "basic_auth_username"]}),
        # Ids are exact, like config keys: no whitespace trimming.
        (http_id, {"clear": [" basic_auth_username "]}),
        (smtp_id, {"clear": ["smtp_host"]}),
        (
            http_id,
            {"config": {"basic_auth_username": "x"}, "clear": ["basic_auth_username"]},
        ),
        (http_id, {"config": ["basic_auth_username"]}),
        (http_id, {"config": "basic_auth_username=x"}),
        # Any non-blank value conflicts with clear, so nothing is deleted.
        *[
            (http_id, {"config": {"basic_auth_username": v}, "clear": ["basic_auth_username"]})
            for v in ("   ", 0, False)
        ],
        # Values that str() would turn into junk secrets.
        *[(http_id, {"config": {"basic_auth_username": v}}) for v in (True, ["x"], {"a": 1})],
    ]
    for profile_id, body in cases:
        response = client.put(f"{_PROFILES}/{profile_id}", json=body, headers=headers)
        assert response.status_code == 400, body

    db_session.expire_all()
    assert get_secret_value(
        db_session, tenant_id="t1", key=secret_ref(http_id, "basic_auth_username")
    ) == "api-user"
    assert get_secret_value(
        db_session, tenant_id="t1", key=secret_ref(smtp_id, "smtp_host")
    ) == "smtp.example.com"


def test_clear_returns_400_when_template_metadata_is_missing(
    client, db_session, monkeypatch
):
    real = template_for("http")
    drifted = {
        **real,
        "profileFields": [
            field for field in real["profileFields"] if field["id"] != "basic_auth_username"
        ],
    }
    monkeypatch.setattr(
        profile_service,
        "template_for",
        lambda connector_type: drifted if connector_type == "http" else template_for(connector_type),
    )
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    profile_id = client.post(_PROFILES, json=_http_profile_body(), headers=headers).get_json()["id"]

    response = client.put(
        f"{_PROFILES}/{profile_id}", json={"clear": ["basic_auth_username"]}, headers=headers
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "validation_error"
    db_session.expire_all()
    assert get_secret_value(
        db_session, tenant_id="t1", key=secret_ref(profile_id, "basic_auth_username")
    ) == "api-user"


def test_create_rejects_non_object_config(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    for config in (["basic_auth_username"], "basic_auth_username=x"):
        response = client.post(
            _PROFILES, json=_http_profile_body(config=config), headers=_headers(token)
        )
        assert response.status_code == 400, config


def test_smtp_show_prefills_settings_but_not_password(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    created = client.post(
        _PROFILES,
        json={
            "connector_type": "smtp",
            "profile_name": "mail",
            "config": {
                "smtp_host": "smtp.example.com",
                "smtp_port": "587",
                "smtp_starttls": "true",
                "email_from": "noreply@example.com",
                "smtp_password": "super-secret",
            },
        },
        headers=headers,
    )
    assert created.status_code == 201

    shown = client.get(f"{_PROFILES}/{created.get_json()['id']}", headers=headers)
    assert shown.status_code == 200
    assert "super-secret" not in json.dumps(shown.get_json())
    assert shown.get_json()["config"] == {
        "smtp_host": "smtp.example.com",
        "smtp_port": "587",
        "smtp_starttls": "true",
        "email_from": "noreply@example.com",
    }


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


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"display_name": "@#%$%%a$#%^&**gf"}, "display_name"),
        ({"display_name": "!!!"}, "display_name"),
        ({"display_name": "   "}, "display_name"),
        ({"display_name": "ab"}, "display_name"),
        ({"display_name": "x" * 61}, "display_name"),
        ({"display_name": "Prod/HTTP"}, "display_name"),
        ({"profile_name": "ab"}, "profile_name"),
        ({"profile_name": "x" * 51}, "profile_name"),
        ({"profile_name": "-bad"}, "profile_name"),
        ({"profile_name": "has space"}, "profile_name"),
    ],
)
def test_create_rejects_invalid_names_with_field_errors(client, db_session, overrides, field):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    response = client.post(_PROFILES, json=_http_profile_body(**overrides), headers=_headers(token))
    assert response.status_code == 400
    body = response.get_json()
    assert body["error_code"] == "validation_error"
    assert list(body["errors"]) == [field]


# Same cases as 'validates display names' in
# m8flow-designer/src/pages/connectors/ConnectorsPage.test.tsx; keep in sync.
@pytest.mark.parametrize(
    ("name", "ok"),
    [
        ("Ⅷ ops", True),  # Ⅷ, letter-number (Nl)
        ("x² ops", True),  # superscript two (No)
        ("〇 ops", True),  # 〇, ideographic zero (Nl)
        ("́abc", False),  # leading combining mark
        ("_abc", False),
        ("Café ops", False),  # NFD accent: combining marks are not allowed
    ],
)
def test_display_name_unicode_rules_match_the_designer(name, ok):
    assert (profile_service._display_name_error(name) is None) is ok


def test_valid_names_save_and_duplicates_get_a_field_error(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    body = _http_profile_body(profile_name="github-prod", display_name="  GitHub Prod (Org A) ")
    created = client.post(_PROFILES, json=body, headers=_headers(token))
    assert created.status_code == 201
    assert created.get_json()["display_name"] == "GitHub Prod (Org A)"

    duplicate = client.post(_PROFILES, json=body, headers=_headers(token))
    assert duplicate.status_code == 409
    assert "github-prod" in duplicate.get_json()["errors"]["profile_name"]


def test_create_maps_concurrent_duplicate_to_409(client, db_session, monkeypatch):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    assert client.post(_PROFILES, json=_http_profile_body(), headers=headers).status_code == 201

    # Simulate a concurrent create: the pre-check misses, so the unique
    # constraint catches the duplicate at flush time.
    real_by_name = profile_service._by_name
    calls = []

    def racing_by_name(*args):
        calls.append(args)
        return None if len(calls) == 1 else real_by_name(*args)

    monkeypatch.setattr(profile_service, "_by_name", racing_by_name)
    duplicate = client.post(_PROFILES, json=_http_profile_body(), headers=headers)
    assert duplicate.status_code == 409
    body = duplicate.get_json()
    assert body["error_code"] == "profile_name_conflict"
    assert "default" in body["errors"]["profile_name"]
    assert len(calls) == 2


def test_create_reports_both_invalid_name_fields(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    response = client.post(
        _PROFILES,
        json=_http_profile_body(profile_name="ab", display_name="!!!"),
        headers=_headers(token),
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error_code"] == "validation_error"
    errors = body["errors"]
    assert set(errors) == {"profile_name", "display_name"}
    assert body["message"] == f"{errors['profile_name']} {errors['display_name']}"


def test_update_validates_changed_names_and_keeps_legacy_ones(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    profile_id = client.post(_PROFILES, json=_http_profile_body(), headers=headers).get_json()["id"]

    for bad in ["@@@", "", "ab"]:
        rejected = client.put(f"{_PROFILES}/{profile_id}", json={"display_name": bad}, headers=headers)
        assert rejected.status_code == 400
        assert list(rejected.get_json()["errors"]) == ["display_name"]

    # A name saved before the rules existed still loads and saves unchanged.
    db_session.get(ConnectorConfigurationModel, profile_id).display_name = "@@legacy"
    db_session.commit()
    kept = client.put(
        f"{_PROFILES}/{profile_id}",
        json={"display_name": "@@legacy", "config": {"basic_auth_username": "other-user"}},
        headers=headers,
    )
    assert kept.status_code == 200
    assert kept.get_json()["display_name"] == "@@legacy"


def test_show_withholds_password_fields_even_if_template_mislabels_them(
    client, db_session, monkeypatch
):
    real = template_for("http")
    mislabeled = {
        **real,
        "profileFields": [
            {**field, "isHighlySensitive": False} for field in real["profileFields"]
        ],
    }
    monkeypatch.setattr(
        profile_service,
        "template_for",
        lambda connector_type: mislabeled if connector_type == "http" else template_for(connector_type),
    )
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    profile_id = client.post(_PROFILES, json=_http_profile_body(), headers=headers).get_json()["id"]

    shown = client.get(f"{_PROFILES}/{profile_id}", headers=headers)
    assert shown.status_code == 200
    _assert_no_secret_leak(shown.get_json())
    assert shown.get_json()["config"] == {"basic_auth_username": "api-user"}


def test_show_withholds_non_sensitive_text_fields_not_marked_prefill_safe(
    client, db_session, monkeypatch
):
    # A credential typed "text" and marked not highly sensitive is still
    # withheld: prefill needs an explicit isPrefillSafe opt-in.
    real = template_for("http")
    fields = []
    for field in real["profileFields"]:
        field = {**field, "isHighlySensitive": False, "type": "text"}
        if field["id"] == "basic_auth_password":
            field.pop("isPrefillSafe", None)
        fields.append(field)
    mislabeled = {**real, "profileFields": fields}
    monkeypatch.setattr(
        profile_service,
        "template_for",
        lambda connector_type: mislabeled if connector_type == "http" else template_for(connector_type),
    )
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    profile_id = client.post(_PROFILES, json=_http_profile_body(), headers=headers).get_json()["id"]

    shown = client.get(f"{_PROFILES}/{profile_id}", headers=headers)
    assert shown.status_code == 200
    _assert_no_secret_leak(shown.get_json())
    assert shown.get_json()["config"] == {"basic_auth_username": "api-user"}


@pytest.mark.parametrize("legacy_name", ["a", "x" * 64])
def test_profiles_with_legacy_identifiers_keep_working(client, db_session, legacy_name):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)
    profile_id = client.post(_PROFILES, json=_http_profile_body(), headers=headers).get_json()["id"]
    # Saved before the 3-50 rule: identifiers are never re-checked after create.
    db_session.get(ConnectorConfigurationModel, profile_id).profile_name = legacy_name
    db_session.commit()

    shown = client.get(f"{_PROFILES}/{profile_id}", headers=headers)
    assert shown.status_code == 200
    assert shown.get_json()["profile_name"] == legacy_name

    updated = client.put(
        f"{_PROFILES}/{profile_id}",
        json={"display_name": "Default HTTP", "config": {"basic_auth_username": "new-user"}},
        headers=headers,
    )
    assert updated.status_code == 200

    resolved = resolve_for_runtime(
        db_session, tenant_id="t1", connector_type="http", profile_name=legacy_name
    )
    assert resolved["basic_auth_username"] == "new-user"

    deleted = client.delete(f"{_PROFILES}/{profile_id}?hard=true", headers=headers)
    assert deleted.status_code == 200
