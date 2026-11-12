from __future__ import annotations

import json

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, import_yaml, sync_groups
from m8flow_backend.models.named_value import NamedValueModel

_COLLECTION = "/v1.0/m8flow/named-values"


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
    return {"Authorization": f"Bearer {token}"}


def test_named_value_crud_returns_plain_value_but_never_sensitive_value(client, db_session, monkeypatch):
    headers = _login_user(
        client,
        db_session,
        username="integrator",
        groups=["tenant-a:integrator"],
        tenant_id="tenant-a",
    )
    provider_values: dict[tuple[str, str], str] = {}

    def set_value(_session, *, tenant_id, variable_id, value, user_id):
        del user_id
        provider_values[(tenant_id, variable_id)] = value

    def delete_value(_session, *, tenant_id, variable_id):
        provider_values.pop((tenant_id, variable_id), None)

    monkeypatch.setattr("m8flow_backend.secrets.named_values.set_configuration_value", set_value)
    monkeypatch.setattr("m8flow_backend.secrets.named_values.delete_configuration_value", delete_value)

    plain = client.post(
        _COLLECTION,
        json={"name": "API_HOST", "value": {"host": "api.example.test"}},
        headers=headers,
    )
    assert plain.status_code == 201
    plain_id = plain.get_json()["id"]
    assert plain.get_json()["value"] == {"host": "api.example.test"}

    sensitive_value = "do-not-return-this-token"
    sensitive = client.post(
        _COLLECTION,
        json={"name": "API_TOKEN", "value": sensitive_value, "is_sensitive": True},
        headers=headers,
    )
    assert sensitive.status_code == 201
    sensitive_body = sensitive.get_json()
    assert sensitive_body["isSensitive"] is True
    assert sensitive_body["isConfigured"] is True
    assert sensitive_body["value"] is None
    assert sensitive_value not in json.dumps(sensitive_body)
    assert provider_values[("tenant-a", sensitive_body["id"])] == sensitive_value
    assert db_session.get(NamedValueModel, sensitive_body["id"]).value is None

    shown = client.get(f"{_COLLECTION}/{sensitive_body['id']}", headers=headers)
    assert shown.status_code == 200
    shown_body = shown.get_json()
    assert shown_body["value"] is None
    assert sensitive_value not in json.dumps(shown_body)

    updated = client.put(
        f"{_COLLECTION}/{plain_id}",
        json={"name": "API_BASE_URL", "value": "https://api.example.test"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.get_json()["name"] == "API_BASE_URL"
    assert updated.get_json()["value"] == "https://api.example.test"

    deleted = client.delete(f"{_COLLECTION}/{sensitive_body['id']}", headers=headers)
    assert deleted.status_code == 200
    assert db_session.get(NamedValueModel, sensitive_body["id"]) is None
    assert ("tenant-a", sensitive_body["id"]) not in provider_values


def test_named_value_names_are_case_insensitively_unique_and_tenant_scoped(client, db_session):
    headers = _login_user(
        client,
        db_session,
        username="integrator",
        groups=["tenant-a:integrator"],
        tenant_id="tenant-a",
    )
    created = client.post(
        _COLLECTION,
        json={"name": "API_TOKEN", "value": "plain"},
        headers=headers,
    )
    assert created.status_code == 201

    duplicate = client.post(
        _COLLECTION,
        json={"name": "api_token", "value": "other"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    other_tenant = ensure_tenant(
        db_session,
        tenant_id="tenant-b",
        slug="tenant-b",
        name="tenant-b",
    )
    del other_tenant
    foreign_row = NamedValueModel(
        id="2e5ae349-0875-4ae9-8b7e-48ab66f1cebe",
        m8f_tenant_id="tenant-b",
        name="API_TOKEN",
        value="tenant-b-value",
        is_sensitive=False,
        is_configured=True,
    )
    db_session.add(foreign_row)
    db_session.commit()

    listing = client.get(_COLLECTION, headers=headers)
    assert listing.status_code == 200
    assert all(row["id"] != foreign_row.id for row in listing.get_json())

    forbidden = client.get(f"{_COLLECTION}/{foreign_row.id}", headers=headers)
    assert forbidden.status_code == 404


def test_tenant_admin_can_read_named_values(client, db_session):
    headers = _login_user(
        client,
        db_session,
        username="tenant-admin",
        groups=["tenant-a:tenant-admin"],
        tenant_id="tenant-a",
    )
    value = NamedValueModel(
        id="c12ba9b9-40ac-48b7-94c8-655ad47d7b27",
        m8f_tenant_id="tenant-a",
        name="API_BASE_URL",
        value="https://api.example.test",
        is_sensitive=False,
        is_configured=True,
    )
    db_session.add(value)
    db_session.commit()

    listing = client.get(_COLLECTION, headers=headers)
    assert listing.status_code == 200
    assert listing.get_json()[0]["name"] == "API_BASE_URL"

    detail = client.get(f"{_COLLECTION}/{value.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.get_json()["value"] == "https://api.example.test"


def test_sensitivity_transitions_require_value_and_never_return_sensitive_data(
    client, db_session, monkeypatch
):
    headers = _login_user(
        client,
        db_session,
        username="integrator-sensitivity-transition",
        groups=["tenant-a:integrator"],
        tenant_id="tenant-a",
    )
    provider_values: dict[tuple[str, str], str] = {}

    def set_value(_session, *, tenant_id, variable_id, value, user_id):
        del user_id
        provider_values[(tenant_id, variable_id)] = value

    def delete_value(_session, *, tenant_id, variable_id):
        provider_values.pop((tenant_id, variable_id), None)

    monkeypatch.setattr("m8flow_backend.secrets.named_values.set_configuration_value", set_value)
    monkeypatch.setattr(
        "m8flow_backend.secrets.named_values.delete_configuration_value", delete_value
    )

    created = client.post(
        _COLLECTION,
        json={"name": "TRANSITION_VALUE", "value": "ordinary-value"},
        headers=headers,
    )
    assert created.status_code == 201
    variable_id = created.get_json()["id"]

    missing_sensitive_value = client.put(
        f"{_COLLECTION}/{variable_id}",
        json={"is_sensitive": True},
        headers=headers,
    )
    assert missing_sensitive_value.status_code == 400
    assert db_session.get(NamedValueModel, variable_id).is_sensitive is False

    secret = "sensitive-transition-sentinel"
    changed_to_sensitive = client.put(
        f"{_COLLECTION}/{variable_id}",
        json={"is_sensitive": True, "value": secret},
        headers=headers,
    )
    assert changed_to_sensitive.status_code == 200
    sensitive_body = changed_to_sensitive.get_json()
    assert sensitive_body["isSensitive"] is True
    assert sensitive_body["value"] is None
    assert secret not in json.dumps(sensitive_body)
    assert provider_values[("tenant-a", variable_id)] == secret

    missing_plain_value = client.put(
        f"{_COLLECTION}/{variable_id}",
        json={"is_sensitive": False},
        headers=headers,
    )
    assert missing_plain_value.status_code == 400
    assert db_session.get(NamedValueModel, variable_id).is_sensitive is True

    changed_to_plain = client.put(
        f"{_COLLECTION}/{variable_id}",
        json={"is_sensitive": False, "value": "new-ordinary-value"},
        headers=headers,
    )
    assert changed_to_plain.status_code == 200
    assert changed_to_plain.get_json()["isSensitive"] is False
    assert changed_to_plain.get_json()["value"] == "new-ordinary-value"
    assert provider_values.get(("tenant-a", variable_id)) is None


def test_named_value_permission_matrix_for_viewer_and_tenant_admin(client, db_session):
    admin_headers = _login_user(
        client,
        db_session,
        username="tenant-admin-named-value-manage",
        groups=["tenant-a:tenant-admin"],
        tenant_id="tenant-a",
    )
    created = client.post(
        _COLLECTION,
        json={"name": "ADMIN_VALUE", "value": "initial"},
        headers=admin_headers,
    )
    assert created.status_code == 201
    variable_id = created.get_json()["id"]

    viewer_headers = _login_user(
        client,
        db_session,
        username="viewer-named-value-read-only",
        groups=["tenant-a:viewer"],
        tenant_id="tenant-a",
    )
    listing = client.get(_COLLECTION, headers=viewer_headers)
    assert listing.status_code == 200
    assert listing.get_json()[0]["name"] == "ADMIN_VALUE"
    assert client.get(
        f"{_COLLECTION}/{variable_id}", headers=viewer_headers
    ).status_code == 200
    assert client.post(
        _COLLECTION,
        json={"name": "VIEWER_VALUE", "value": "not-allowed"},
        headers=viewer_headers,
    ).status_code == 403
    assert client.put(
        f"{_COLLECTION}/{variable_id}",
        json={"value": "not-allowed"},
        headers=viewer_headers,
    ).status_code == 403
    assert client.delete(f"{_COLLECTION}/{variable_id}", headers=viewer_headers).status_code == 403

    # Switch the active tenant back after the viewer request and verify the
    # tenant-admin can manage the same row.
    admin_headers = _login_user(
        client,
        db_session,
        username="tenant-admin-named-value-manage",
        groups=["tenant-a:tenant-admin"],
        tenant_id="tenant-a",
    )
    updated = client.put(
        f"{_COLLECTION}/{variable_id}",
        json={"value": "updated"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.get_json()["value"] == "updated"
