"""Vault secret backend: CRUD on a fake KV store, AppRole provisioning, tenant-create hook."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from m8flow_backend.errors import ApiError
from m8flow_backend.identity import ensure_user
from m8flow_backend.models.native import SecretModel
from m8flow_backend.secrets.provider import register_secret_provider
from m8flow_backend.identity import create_tenant_if_not_exists


class MemoryKv:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, object]] = {}
        self.fail: Exception | None = None

    def put_document(self, path: str, document: dict[str, object]) -> None:
        if self.fail is not None:
            raise self.fail
        self.docs[path] = dict(document)

    def get_document(self, path: str) -> dict[str, object] | None:
        if self.fail is not None:
            raise self.fail
        document = self.docs.get(path)
        return None if document is None else dict(document)

    def list_names(self, path: str) -> list[str]:
        if self.fail is not None:
            raise self.fail
        prefix = path.strip("/") + "/"
        names: set[str] = set()
        for stored in self.docs:
            if stored.startswith(prefix):
                names.add(stored[len(prefix) :].split("/", 1)[0])
        return sorted(names)

    def delete_document(self, path: str) -> bool:
        if self.fail is not None:
            raise self.fail
        return self.docs.pop(path, None) is not None


class MemoryControlPlane:
    def __init__(self) -> None:
        self.policies: dict[str, str] = {}
        self.roles: dict[str, dict[str, object]] = {}
        self.secret_id_calls: list[str] = []

    def write_policy(self, name: str, policy: str) -> None:
        self.policies[name] = policy

    def read_approle(self, role_name: str, *, mount: str):
        payload = self.roles.get(role_name)
        return None if payload is None else {"data": payload}

    def write_approle(
        self,
        role_name: str,
        *,
        mount: str,
        token_policies: list[str],
        token_no_default_policy: bool = True,
        secret_id_num_uses: int | None = None,
        secret_id_ttl: str | int | None = None,
        token_ttl: str | int | None = None,
        token_max_ttl: str | int | None = None,
    ) -> None:
        self.roles[role_name] = {
            "token_policies": list(token_policies),
            "mount": mount,
            "token_no_default_policy": token_no_default_policy,
            "secret_id_num_uses": secret_id_num_uses,
            "secret_id_ttl": secret_id_ttl,
            "token_ttl": token_ttl,
            "token_max_ttl": token_max_ttl,
        }

    def read_approle_role_id(self, role_name: str, *, mount: str) -> str:
        return f"role-id-for-{role_name}"

    def mint_approle_secret_id(self, role_name: str, *, mount: str):
        self.secret_id_calls.append(role_name)
        return SimpleNamespace(
            secret_id=f"secret-id-for-{role_name}",
            secret_id_accessor=f"accessor-for-{role_name}",
        )


@pytest.fixture(autouse=True)
def _restore_vault_provider():
    from m8flow_backend.secrets.vault import VaultSecretProvider

    register_secret_provider("vault", VaultSecretProvider)
    yield
    register_secret_provider("vault", VaultSecretProvider)


def _user_session(username: str = "alice"):
    return SimpleNamespace(get=lambda *_a, **_k: SimpleNamespace(username=username))


def _provider(store: MemoryKv, stores_by_tenant: dict[str, MemoryKv] | None = None):
    from m8flow_backend.secrets.vault import VaultSecretProvider

    if stores_by_tenant is None:
        return VaultSecretProvider(store=store)
    return VaultSecretProvider(store_for_tenant=lambda tenant_id: stores_by_tenant[tenant_id])


def test_vault_kind_is_selected_when_enabled(monkeypatch):
    from m8flow_backend.secrets.provider import resolved_secret_backend_kind

    monkeypatch.delenv("M8FLOW_SECRET_BACKEND_KIND", raising=False)
    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    assert resolved_secret_backend_kind() == "vault"

    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "false")
    assert resolved_secret_backend_kind() == "database"

    monkeypatch.setenv("M8FLOW_SECRET_BACKEND_KIND", "vault")
    assert resolved_secret_backend_kind() == "vault"


def test_vault_create_stores_value_only_in_kv(db_session, monkeypatch):
    from m8flow_backend.secrets import add_secret, get_secret, get_secret_value

    monkeypatch.setenv("M8FLOW_SECRET_BACKEND_KIND", "vault")

    store = MemoryKv()
    register_secret_provider("vault", lambda: _provider(store))
    user = ensure_user(
        db_session,
        username="alice",
        service="https://example.test/realms/m8flow",
        service_id="alice",
    )

    record = add_secret(
        db_session, tenant_id="tenant-a", key="SMTP_PASSWORD", value="super-secret", user_id=user.id
    )
    path = "m8flow/tenants/tenant-a/secrets/SMTP_PASSWORD"
    document = store.docs[path]
    assert document["value"] == "super-secret"
    assert document["tenant_id"] == "tenant-a"
    assert document["user_id"] == user.id
    assert document["username"] == "alice"
    assert record.key == "SMTP_PASSWORD"
    assert "value" not in record.to_dict()
    assert get_secret(db_session, tenant_id="tenant-a", key="SMTP_PASSWORD").key == "SMTP_PASSWORD"
    assert get_secret_value(db_session, tenant_id="tenant-a", key="SMTP_PASSWORD") == "super-secret"
    assert db_session.query(SecretModel).count() == 0


def test_vault_uses_tenant_scoped_stores():
    from m8flow_backend.secrets.vault import VaultSecretProvider

    tenant_a = MemoryKv()
    tenant_b = MemoryKv()
    provider = VaultSecretProvider(
        store_for_tenant=lambda tenant_id: {"tenant-a": tenant_a, "tenant-b": tenant_b}[tenant_id]
    )
    session = _user_session()
    provider.add(session, tenant_id="tenant-a", key="API_TOKEN", value="a-value", user_id=1)
    provider.add(session, tenant_id="tenant-b", key="API_TOKEN", value="b-value", user_id=1)
    assert tenant_a.docs["m8flow/tenants/tenant-a/secrets/API_TOKEN"]["value"] == "a-value"
    assert tenant_b.docs["m8flow/tenants/tenant-b/secrets/API_TOKEN"]["value"] == "b-value"
    assert provider.get_value(session, tenant_id="tenant-a", key="API_TOKEN") == "a-value"
    assert provider.get_value(session, tenant_id="tenant-b", key="API_TOKEN") == "b-value"


def test_vault_update_and_delete_and_duplicate(db_session, monkeypatch):
    from m8flow_backend.secrets import add_secret, delete_secret, get_secret_value, list_secrets, update_secret

    monkeypatch.setenv("M8FLOW_SECRET_BACKEND_KIND", "vault")

    store = MemoryKv()
    register_secret_provider("vault", lambda: _provider(store))
    user = ensure_user(
        db_session,
        username="alice",
        service="https://example.test/realms/m8flow",
        service_id="alice",
    )
    add_secret(db_session, tenant_id="t1", key="API_TOKEN", value="one", user_id=user.id)
    with pytest.raises(ApiError) as duplicate:
        add_secret(db_session, tenant_id="t1", key="API_TOKEN", value="two", user_id=user.id)
    assert duplicate.value.error_code == "create_secret_error"
    update_secret(db_session, tenant_id="t1", key="API_TOKEN", value="rotated")
    assert get_secret_value(db_session, tenant_id="t1", key="API_TOKEN") == "rotated"
    listed = list_secrets(db_session, tenant_id="t1")
    assert [row.key for row in listed.records] == ["API_TOKEN"]
    assert all("value" not in row.to_dict() for row in listed.records)
    delete_secret(db_session, tenant_id="t1", key="API_TOKEN")
    assert get_secret_value(db_session, tenant_id="t1", key="API_TOKEN") is None
    with pytest.raises(ApiError) as missing:
        update_secret(db_session, tenant_id="t1", key="API_TOKEN", value="nope")
    assert missing.value.error_code == "update_secret_error"


def test_vault_transport_error_does_not_leak_secret_text():
    store = MemoryKv()
    store.fail = RuntimeError("secret_id=secret-123 value=demo-secret")
    provider = _provider(store)
    with pytest.raises(ApiError) as exc_info:
        provider.add(_user_session(), tenant_id="t1", key="API_TOKEN", value="vault-value", user_id=1)
    assert exc_info.value.status_code == 503
    assert "secret-123" not in exc_info.value.message
    assert "demo-secret" not in exc_info.value.message
    assert "vault-value" not in exc_info.value.message


def test_provision_tenant_identity_creates_policy_and_approle(monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultIdentity, provision_tenant_identity

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_SECRET_ID_NUM_USES", "1")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_SECRET_ID_TTL", "10m")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_TOKEN_TTL", "10m")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_TOKEN_MAX_TTL", "30m")

    control = MemoryControlPlane()
    result = provision_tenant_identity("org-uuid-123", control=control)
    assert result == TenantVaultIdentity(
        tenant_id="org-uuid-123",
        policy_name="m8flow-tenant-policy-org-uuid-123",
        role_name="m8flow-tenant-role-org-uuid-123",
        role_id="role-id-for-m8flow-tenant-role-org-uuid-123",
        secret_id="secret-id-for-m8flow-tenant-role-org-uuid-123",
        secret_id_accessor="accessor-for-m8flow-tenant-role-org-uuid-123",
        created_new_secret_id=True,
    )
    assert control.policies["m8flow-tenant-policy-org-uuid-123"] == (
        'path "kv/data/m8flow/tenants/org-uuid-123/secrets/*" {\n'
        '  capabilities = ["create", "read", "update", "delete"]\n'
        "}\n\n"
        'path "kv/metadata/m8flow/tenants/org-uuid-123/secrets" {\n'
        '  capabilities = ["list", "read"]\n'
        "}\n\n"
        'path "kv/metadata/m8flow/tenants/org-uuid-123/secrets/*" {\n'
        '  capabilities = ["list", "read", "delete"]\n'
        "}\n"
    )
    assert control.roles["m8flow-tenant-role-org-uuid-123"]["token_policies"] == [
        "m8flow-tenant-policy-org-uuid-123"
    ]
    assert control.roles["m8flow-tenant-role-org-uuid-123"]["secret_id_num_uses"] == 1
    assert control.secret_id_calls == ["m8flow-tenant-role-org-uuid-123"]


def test_provision_does_not_rotate_secret_for_existing_role(monkeypatch):
    from m8flow_backend.secrets.provisioning import provision_tenant_identity

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    control = MemoryControlPlane()
    control.roles["m8flow-tenant-role-org-uuid-123"] = {
        "token_policies": ["m8flow-tenant-policy-org-uuid-123"]
    }
    result = provision_tenant_identity("org-uuid-123", control=control)
    assert result.secret_id is None
    assert result.created_new_secret_id is False
    assert control.secret_id_calls == []


def test_provision_sanitizes_names_and_encodes_tenant_path(monkeypatch):
    from m8flow_backend.secrets.provisioning import provision_tenant_identity

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle-custom")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "tenant policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "tenant/role")
    control = MemoryControlPlane()
    spaced = provision_tenant_identity("tenant / blue", control=control)
    assert spaced.policy_name == "tenant-policy-tenant-blue"
    assert spaced.role_name == "tenant-role-tenant-blue"
    assert control.roles[spaced.role_name]["mount"] == "approle-custom"

    encoded = MemoryControlPlane()
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    provision_tenant_identity("tenant+/blue*west", control=encoded)
    policy = encoded.policies["m8flow-tenant-policy-tenant-blue-west"]
    assert "kv/data/m8flow/tenants/tenant%2B%2Fblue%2Awest/secrets/*" in policy


def test_provision_rejects_empty_tenant_id(monkeypatch):
    from m8flow_backend.secrets.provisioning import provision_tenant_identity

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    with pytest.raises(ValueError, match="tenant_id must not be empty"):
        provision_tenant_identity("   ", control=MemoryControlPlane())


def test_new_tenant_is_removed_when_vault_provisioning_fails(app, db_session, monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultProvisioningError
    from m8flow_bpmn_core.models.tenant import M8flowTenantModel

    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    monkeypatch.delenv("M8FLOW_SECRET_BACKEND_KIND", raising=False)

    def boom(_tenant_id: str, control=None):
        raise TenantVaultProvisioningError("policy write failed")

    monkeypatch.setattr("m8flow_backend.secrets.provisioning.provision_tenant_identity", boom)
    with app.test_request_context("/"):
        from flask import g

        g.db_session = db_session
        with pytest.raises(TenantVaultProvisioningError):
            create_tenant_if_not_exists("org-1", name="Org", slug="org")
    assert db_session.get(M8flowTenantModel, "org-1") is None


def test_vault_disabled_does_not_provision_on_tenant_create(app, db_session, monkeypatch):
    from m8flow_bpmn_core.models.tenant import M8flowTenantModel

    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("M8FLOW_SECRET_BACKEND_KIND", raising=False)
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.provision_tenant_identity",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not provision")),
    )
    with app.test_request_context("/"):
        from flask import g

        g.db_session = db_session
        create_tenant_if_not_exists("org-2", name="Org 2", slug="org-2")
    assert db_session.get(M8flowTenantModel, "org-2") is not None


def test_create_realm_cleans_up_when_vault_provisioning_fails(app, db_session, monkeypatch):
    from m8flow_backend.integrations.auth.base.models import Tenant, TenantRef
    from m8flow_backend.secrets.provisioning import TenantVaultProvisioningError
    from m8flow_bpmn_core.models.tenant import M8flowTenantModel

    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    monkeypatch.delenv("M8FLOW_SECRET_BACKEND_KIND", raising=False)
    deleted: list[str] = []

    class _Admin:
        def create_tenant(self, *, alias: str, name: str | None = None):
            return Tenant(ref=TenantRef(id="org-fail", alias=alias, name=name or alias), display_name=name or alias)

        def delete_tenant(self, tenant_ref: TenantRef) -> None:
            deleted.append(tenant_ref.id or "")

    monkeypatch.setattr(
        "m8flow_backend.routes.keycloak_controller.get_auth_provider",
        lambda: SimpleNamespace(directory_admin=_Admin()),
    )
    monkeypatch.setattr(
        "m8flow_backend.routes.keycloak_controller.allow_uri",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.provision_tenant_identity",
        lambda *_a, **_k: (_ for _ in ()).throw(TenantVaultProvisioningError("policy write failed")),
    )
    with app.test_request_context("/tenant-realms", method="POST", json={"slug": "acme"}):
        from flask import g

        g.user = SimpleNamespace(username="root", groups=[])
        g.db_session = db_session
        from m8flow_backend.routes.keycloak_controller import create_realm

        body, status = create_realm({"slug": "acme"})
    assert status == 502
    assert "Vault provisioning" in body["detail"]
    assert db_session.get(M8flowTenantModel, "org-fail") is None
    assert deleted == ["org-fail"]
