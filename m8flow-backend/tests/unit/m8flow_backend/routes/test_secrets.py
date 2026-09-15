from __future__ import annotations

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, import_yaml, sync_groups
from m8flow_backend.models.native import SecretModel
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME


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


def test_integrator_crud_never_returns_value(client, db_session):
    user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    headers = _headers(token)

    created = client.post("/v1.0/secrets", json={"key": "API_TOKEN", "value": "super-secret"}, headers=headers)
    assert created.status_code == 201
    body = created.get_json()
    assert body["key"] == "API_TOKEN"
    assert body["user_id"] == user.id
    assert "value" not in body

    listed = client.get("/v1.0/secrets", headers=headers)
    assert listed.status_code == 200
    payload = listed.get_json()
    assert payload["pagination"]["total"] == 1
    row = payload["results"][0]
    assert row["key"] == "API_TOKEN"
    assert row["username"] == "integrator"
    assert "value" not in row

    shown = client.get("/v1.0/secrets/API_TOKEN", headers=headers)
    assert shown.status_code == 200
    assert "value" not in shown.get_json()

    disabled = client.get("/v1.0/secrets/API_TOKEN/show", headers=headers)
    assert disabled.status_code == 404
    assert disabled.get_json()["error_code"] == "secret_value_retrieval_disabled"
    query_disabled = client.get("/v1.0/secrets/API_TOKEN?show_secret_value=true", headers=headers)
    assert query_disabled.status_code == 404
    assert query_disabled.get_json()["error_code"] == "secret_value_retrieval_disabled"

    updated = client.put("/v1.0/secrets/API_TOKEN", json={"value": "rotated"}, headers=headers)
    assert updated.status_code == 200
    assert updated.get_json() == {"ok": True}

    missing_update = client.put("/v1.0/secrets/NO_SUCH", json={"value": "x"}, headers=headers)
    assert missing_update.status_code == 404
    assert missing_update.get_json()["error_code"] == "update_secret_error"

    duplicate = client.post("/v1.0/secrets", json={"key": "API_TOKEN", "value": "again"}, headers=headers)
    assert duplicate.status_code == 409

    deleted = client.delete("/v1.0/secrets/API_TOKEN", headers=headers)
    assert deleted.status_code == 200
    after = client.get("/v1.0/secrets", headers=headers)
    assert after.get_json()["results"] == []


def test_viewer_lists_without_values_and_cannot_write(client, db_session):
    _integrator, integrator_token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    client.post(
        "/v1.0/secrets",
        json={"key": "SMTP_USER", "value": "hidden"},
        headers=_headers(integrator_token),
    )

    _viewer, viewer_token = _login_user(
        client, db_session, username="viewer", groups=["t1:viewer"], tenant_id="t1"
    )
    headers = _headers(viewer_token)
    listed = client.get("/v1.0/secrets", headers=headers)
    assert listed.status_code == 200
    results = listed.get_json()["results"]
    assert [row["key"] for row in results] == ["SMTP_USER"]
    assert all("value" not in row for row in results)

    created = client.post("/v1.0/secrets", json={"key": "NOPE", "value": "x"}, headers=headers)
    assert created.status_code == 403
    updated = client.put("/v1.0/secrets/SMTP_USER", json={"value": "x"}, headers=headers)
    assert updated.status_code == 403


def test_editor_cannot_manage_secrets(client, db_session):
    _user, token = _login_user(
        client, db_session, username="editor", groups=["t1:editor"], tenant_id="t1"
    )
    headers = _headers(token)
    listed = client.get("/v1.0/secrets", headers=headers)
    assert listed.status_code == 200
    assert listed.get_json()["results"] == []
    created = client.post("/v1.0/secrets", json={"key": "API_TOKEN", "value": "x"}, headers=headers)
    assert created.status_code == 403
    updated = client.put("/v1.0/secrets/API_TOKEN", json={"value": "x"}, headers=headers)
    assert updated.status_code == 403


def test_secrets_are_isolated_across_tenants(client, db_session):
    _user_a, token_a = _login_user(
        client, db_session, username="integrator-a", groups=["t1:integrator"], tenant_id="t1"
    )
    created = client.post(
        "/v1.0/secrets", json={"key": "SHARED_KEY", "value": "tenant-a"}, headers=_headers(token_a)
    )
    assert created.status_code == 201

    _user_b, token_b = _login_user(
        client, db_session, username="integrator-b", groups=["t2:integrator"], tenant_id="t2"
    )
    listed_b = client.get("/v1.0/secrets", headers=_headers(token_b))
    assert listed_b.get_json()["results"] == []
    shown_b = client.get("/v1.0/secrets/SHARED_KEY", headers=_headers(token_b))
    assert shown_b.status_code == 404


def test_invalid_secret_key_is_rejected(client, db_session):
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    created = client.post(
        "/v1.0/secrets",
        json={"key": "not-a-word", "value": "x"},
        headers=_headers(token),
    )
    assert created.status_code == 400
    assert created.get_json()["error_code"] == "validation_error"


def test_database_provider_encrypts_at_rest(db_session):
    from m8flow_backend.secrets import add_secret, get_secret_value

    ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(
        db_session,
        username="integrator",
        service="https://example.test/realms/m8flow",
        service_id="integrator",
    )
    record = add_secret(
        db_session, tenant_id="t1", key="API_TOKEN", value="super-secret", user_id=user.id
    )
    db_session.flush()
    row = db_session.get(SecretModel, record.id)
    assert row is not None
    assert row.value != "super-secret"
    assert get_secret_value(db_session, tenant_id="t1", key="API_TOKEN") == "super-secret"


def test_unknown_backend_kind_fails_closed(client, db_session, monkeypatch):
    monkeypatch.setenv("M8FLOW_SECRET_BACKEND_KIND", "nosuch")
    _user, token = _login_user(
        client, db_session, username="integrator", groups=["t1:integrator"], tenant_id="t1"
    )
    listed = client.get("/v1.0/secrets", headers=_headers(token))
    assert listed.status_code == 500
    assert listed.get_json()["error_code"] == "secret_backend_unavailable"


def test_provider_can_be_swapped_for_another_store(db_session):
    from m8flow_backend.secrets.provider import SecretListPage, SecretRecord, get_secret_provider, register_secret_provider

    store: dict[tuple[str, str], tuple[str, int]] = {}

    class MemorySecretProvider:
        def add(self, session, *, tenant_id, key, value, user_id):
            store[(tenant_id, key)] = (value, user_id)
            return SecretRecord(
                id=f"{tenant_id}:{key}",
                key=key,
                user_id=user_id,
                tenant_id=tenant_id,
                created_at_in_seconds=0,
                updated_at_in_seconds=0,
            )

        def get(self, session, *, tenant_id, key):
            raise AssertionError("not needed")

        def get_value(self, session, *, tenant_id, key):
            held = store.get((tenant_id, key))
            return None if held is None else held[0]

        def update(self, session, *, tenant_id, key, value):
            raise AssertionError("not needed")

        def delete(self, session, *, tenant_id, key):
            raise AssertionError("not needed")

        def list(self, session, *, tenant_id, page=1, per_page=100):
            return SecretListPage(records=(), total=0, page=page, per_page=per_page)

        def list_keys(self, session, *, tenant_id):
            return [key for stored_tenant, key in store if stored_tenant == tenant_id]

    register_secret_provider("memory", MemorySecretProvider)
    provider = get_secret_provider("memory")
    created = provider.add(db_session, tenant_id="t1", key="FROM_MEMORY", value="mem-value", user_id=9)
    assert created.id == "t1:FROM_MEMORY"
    assert store[("t1", "FROM_MEMORY")] == ("mem-value", 9)
    assert provider.get_value(db_session, tenant_id="t1", key="FROM_MEMORY") == "mem-value"
    from m8flow_backend.secrets import get_secret_value

    assert get_secret_value(db_session, tenant_id="t1", key="FROM_MEMORY") is None
