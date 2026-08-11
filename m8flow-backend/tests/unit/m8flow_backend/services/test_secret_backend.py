from __future__ import annotations
# ruff: noqa: E402

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, g

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (repo_root, extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from m8flow_backend.models.user import UserModel
from m8flow_backend.services import secret_backend as secret_backend_module
from m8flow_backend.services.secret_backend_contract import SecretBackend, SecretRecord
from m8flow_backend.services.secret_backend import (
    LegacyDatabaseSecretBackend,
    ResolvedSecret,
    VaultBackedSecretBackend,
    get_secret_backend,
)
from m8flow_backend.services.tenant_scoped_vault_client_provider import TenantScopedVaultClientError
from m8flow_backend.services.vault_client import VaultConnectionError
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import add_listeners, db


class FakeCipher:
    def encrypt(self, value: bytes) -> bytes:
        return b"enc:" + value

    def decrypt(self, value: bytes) -> bytes:
        if not value.startswith(b"enc:"):
            raise ValueError("unexpected ciphertext")
        return value[4:]


class FakeVaultClient:
    def __init__(self) -> None:
        self.storage: dict[str, dict[str, object]] = {}
        self.store_calls: list[tuple[str, dict[str, object]]] = []
        self.delete_calls: list[str] = []
        self.retrieve_calls: list[str] = []
        self.list_calls: list[str] = []
        self.fail_store: Exception | None = None
        self.fail_delete: Exception | None = None
        self.fail_retrieve: Exception | None = None
        self.fail_list: Exception | None = None

    def store_secret_document(self, path: str, document: dict[str, object]) -> dict[str, object]:
        self.store_calls.append((path, dict(document)))
        if self.fail_store is not None:
            raise self.fail_store
        self.storage[path] = dict(document)
        return {"data": {"path": path}}

    def retrieve_secret_document(self, path: str) -> dict[str, object] | None:
        self.retrieve_calls.append(path)
        if self.fail_retrieve is not None:
            raise self.fail_retrieve
        document = self.storage.get(path)
        return None if document is None else dict(document)

    def list_secret_names(self, path: str) -> list[str]:
        self.list_calls.append(path)
        if self.fail_list is not None:
            raise self.fail_list

        prefix = f"{path.strip('/')}/"
        entries: set[str] = set()
        for stored_path in self.storage:
            if not stored_path.startswith(prefix):
                continue
            remainder = stored_path[len(prefix) :]
            if not remainder:
                continue
            first_component, _separator, suffix = remainder.partition("/")
            entries.add(f"{first_component}/" if suffix else first_component)
        return sorted(entries)

    def delete_secret(self, path: str) -> bool:
        self.delete_calls.append(path)
        if self.fail_delete is not None:
            raise self.fail_delete
        existed = path in self.storage
        self.storage.pop(path, None)
        return existed

    def store_secret(self, path: str, value: str) -> dict[str, object]:
        return self.store_secret_document(path, {"value": value})

    def retrieve_secret(self, path: str) -> str | None:
        document = self.retrieve_secret_document(path)
        if document is None:
            return None
        value = document.get("value")
        return None if value is None else str(value)


class FakeTenantScopedVaultClientProvider:
    def __init__(self, default_client: FakeVaultClient) -> None:
        self.default_client = default_client
        self.calls: list[str] = []
        self.clients_by_tenant: dict[str, FakeVaultClient] = {}
        self.errors_by_tenant: dict[str, Exception] = {}

    def for_tenant(self, tenant_id: str):
        self.calls.append(tenant_id)
        error = self.errors_by_tenant.get(tenant_id)
        if error is not None:
            raise error
        vault_client = self.clients_by_tenant.get(tenant_id, self.default_client)
        return SimpleNamespace(vault_client=vault_client)


@pytest.fixture
def app():
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    app.config["SPIFFWORKFLOW_BACKEND_ENCRYPTION_LIB"] = "cryptography"
    app.config["CIPHER"] = FakeCipher()
    app.config["M8FLOW_VAULT_SECRET_PATH_PREFIX"] = "m8flow"
    app.config["M8FLOW_SECRET_BACKEND_KIND"] = "vault"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        add_listeners()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def tenants(app):
    with app.app_context():
        tenant_a = M8flowTenantModel(
            id="tenant-a",
            name="Tenant A",
            slug="tenant-a",
            status=TenantStatus.ACTIVE,
            created_by="system",
            modified_by="system",
        )
        tenant_b = M8flowTenantModel(
            id="tenant-b",
            name="Tenant B",
            slug="tenant-b",
            status=TenantStatus.ACTIVE,
            created_by="system",
            modified_by="system",
        )
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()
        return tenant_a.id, tenant_b.id


@pytest.fixture
def user(app):
    with app.app_context():
        user = UserModel(username="alice", email="alice@example.com", service="local", service_id="alice")
        db.session.add(user)
        db.session.commit()
        return user.id


def _backend(
    fake_vault: FakeVaultClient,
    provider: FakeTenantScopedVaultClientProvider | None = None,
) -> VaultBackedSecretBackend:
    return VaultBackedSecretBackend(
        vault_client=fake_vault,
        tenant_vault_client_provider=provider or FakeTenantScopedVaultClientProvider(fake_vault),
    )


def test_vault_mode_create_stores_value_and_metadata_only_in_vault(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()

    with app.app_context():
        with app.test_request_context("/"):
            g.m8flow_tenant_id = tenants[0]
            secret = _backend(fake_vault).add_secret("SMTP_PASSWORD", "super-secret", user)

        expected_path = f"m8flow/tenants/{tenants[0]}/secrets/SMTP_PASSWORD"
        stored_document = fake_vault.storage[expected_path]

        assert stored_document["value"] == "super-secret"
        assert stored_document["tenant_id"] == tenants[0]
        assert stored_document["user_id"] == user
        assert stored_document["username"] == "alice"
        assert isinstance(stored_document["id"], str)
        assert stored_document["created_at_in_seconds"] == stored_document["updated_at_in_seconds"]
        assert secret.key == "SMTP_PASSWORD"
        assert secret.value != "super-secret"
        assert secret.to_dict()["user_id"] == user


def test_vault_mode_get_secret_value_reads_from_vault(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend = _backend(fake_vault)
        backend.add_secret("API_TOKEN", "vault-value", user)
        resolved = backend.get_secret_value("API_TOKEN")

    assert resolved == "vault-value"


def test_vault_mode_uses_tenant_scoped_clients_for_data_plane(app, tenants, user) -> None:
    broker_vault = FakeVaultClient()
    tenant_a_vault = FakeVaultClient()
    tenant_b_vault = FakeVaultClient()
    provider = FakeTenantScopedVaultClientProvider(broker_vault)
    provider.clients_by_tenant = {
        tenants[0]: tenant_a_vault,
        tenants[1]: tenant_b_vault,
    }
    backend = _backend(broker_vault, provider=provider)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("API_TOKEN", "tenant-a-value", user)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[1]
        backend.add_secret("API_TOKEN", "tenant-b-value", user)

    tenant_a_path = f"m8flow/tenants/{tenants[0]}/secrets/API_TOKEN"
    tenant_b_path = f"m8flow/tenants/{tenants[1]}/secrets/API_TOKEN"
    assert broker_vault.storage == {}
    assert tenant_a_vault.storage[tenant_a_path]["value"] == "tenant-a-value"
    assert tenant_a_vault.storage[tenant_a_path]["tenant_id"] == tenants[0]
    assert tenant_b_vault.storage[tenant_b_path]["value"] == "tenant-b-value"
    assert tenant_b_vault.storage[tenant_b_path]["tenant_id"] == tenants[1]
    assert provider.calls == [tenants[0], tenants[1]]


def test_vault_mode_returns_runtime_error_when_tenant_client_cannot_be_resolved(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    provider = FakeTenantScopedVaultClientProvider(fake_vault)
    provider.errors_by_tenant[tenants[0]] = TenantScopedVaultClientError("tenant approle is missing")
    backend = _backend(fake_vault, provider=provider)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        with pytest.raises(ApiError) as exc_info:
            backend.add_secret("API_TOKEN", "vault-value", user)

    assert exc_info.value.error_code == "vault_create_error"
    assert "tenant approle is missing" in exc_info.value.message


def test_vault_mode_does_not_fallback_to_legacy_secret_table(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)
    secret_table = db.metadata.tables["secret"]

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("SMTP_PASSWORD", "vault-value", user)

        db.session.execute(
            secret_table.insert().values(
                key="SMTP_PASSWORD",
                value="enc:legacy-value",
                user_id=user,
                m8f_tenant_id=tenants[0],
            )
        )
        db.session.commit()

        fake_vault.fail_retrieve = VaultConnectionError("vault unavailable")
        with pytest.raises(ApiError) as exc_info:
            backend.get_secret("SMTP_PASSWORD")

    assert exc_info.value.error_code == "vault_read_error"


def test_secret_names_are_unique_within_tenant_but_reusable_across_tenants(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.app_context():
        with app.test_request_context("/"):
            g.m8flow_tenant_id = tenants[0]
            backend.add_secret("SHARED_KEY", "tenant-a-value", user)
            with pytest.raises(ApiError) as exc_info:
                backend.add_secret("SHARED_KEY", "duplicate", user)
            assert exc_info.value.error_code == "create_secret_error"
            assert fake_vault.storage[f"m8flow/tenants/{tenants[0]}/secrets/SHARED_KEY"]["value"] == "tenant-a-value"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = tenants[1]
            backend.add_secret("SHARED_KEY", "tenant-b-value", user)

        assert len(fake_vault.storage) == 2


def test_tenant_a_cannot_resolve_tenant_b_secret(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("TENANT_SECRET", "tenant-a-value", user)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[1]
        with pytest.raises(ApiError) as exc_info:
            backend.get_secret("TENANT_SECRET")

    assert exc_info.value.error_code == "missing_secret_error"


def test_vault_path_uses_secret_name_and_moves_on_rename(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        created = backend.add_secret("OLD_NAME", "initial", user)
        original_path = f"m8flow/tenants/{tenants[0]}/secrets/OLD_NAME"
        renamed_path = f"m8flow/tenants/{tenants[0]}/secrets/NEW_NAME"

        backend.update_secret("OLD_NAME", "updated", user, new_key="NEW_NAME")
        resolved = backend.get_secret("NEW_NAME")
        with pytest.raises(ApiError):
            backend.get_secret("OLD_NAME")

    assert fake_vault.store_calls[0][0] == original_path
    assert fake_vault.store_calls[-1][0] == renamed_path
    assert fake_vault.delete_calls[-1] == original_path
    assert fake_vault.storage[renamed_path]["value"] == "updated"
    assert fake_vault.storage[renamed_path]["id"] == created.id
    assert resolved.key == "NEW_NAME"


def test_rename_to_existing_secret_is_rejected_before_touching_vault(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("OLD_NAME", "initial", user)
        backend.add_secret("EXISTING_NAME", "existing", user)
        store_calls_before = list(fake_vault.store_calls)

        with pytest.raises(ApiError) as exc_info:
            backend.update_secret("OLD_NAME", "updated", user, new_key="EXISTING_NAME")

    assert exc_info.value.error_code == "update_secret_error"
    assert fake_vault.store_calls == store_calls_before
    assert fake_vault.storage[f"m8flow/tenants/{tenants[0]}/secrets/OLD_NAME"]["value"] == "initial"
    assert fake_vault.storage[f"m8flow/tenants/{tenants[0]}/secrets/EXISTING_NAME"]["value"] == "existing"


def test_missing_vault_value_with_present_document_is_returned_as_not_found(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("API_TOKEN", "vault-value", user)
        fake_vault.storage[f"m8flow/tenants/{tenants[0]}/secrets/API_TOKEN"].pop("value", None)
        with pytest.raises(ApiError) as exc_info:
            backend.get_secret("API_TOKEN")

    assert exc_info.value.error_code == "vault_secret_value_missing"
    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Unable to locate the Vault secret value for key: API_TOKEN."


def test_delete_removes_vault_document_and_tolerates_missing_vault_value(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.app_context():
        with app.test_request_context("/"):
            g.m8flow_tenant_id = tenants[0]
            backend.add_secret("API_TOKEN", "vault-value", user)
            backend.delete_secret("API_TOKEN", user)
            assert "m8flow/tenants/tenant-a/secrets/API_TOKEN" not in fake_vault.storage

            backend.add_secret("API_TOKEN", "vault-value", user)
            fake_vault.storage["m8flow/tenants/tenant-a/secrets/API_TOKEN"].pop("value", None)
            backend.delete_secret("API_TOKEN", user)


def test_list_responses_do_not_include_secret_values(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("API_TOKEN", "vault-value", user)
        payload = backend.serialize_secret_list_result()

    assert payload["results"][0]["key"] == "API_TOKEN"
    assert payload["results"][0]["username"] == "alice"
    assert payload["results"][0]["tenantName"] == "Tenant A"
    assert "value" not in payload["results"][0]


def test_list_without_tenant_context_discovers_all_vault_tenants(app, tenants, user, monkeypatch) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("TENANT_A_SECRET", "tenant-a-value", user)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[1]
        backend.add_secret("TENANT_B_SECRET", "tenant-b-value", user)

    monkeypatch.setattr(secret_backend_module, "current_tenant_id_or_none", lambda: None)

    with app.test_request_context("/"):
        payload = backend.serialize_secret_list_result()

    returned_keys = {(row["tenantId"], row["key"]) for row in payload["results"]}
    assert returned_keys == {
        (tenants[0], "TENANT_A_SECRET"),
        (tenants[1], "TENANT_B_SECRET"),
    }


def test_legacy_vault_document_without_metadata_still_resolves(app, tenants) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)
    path = f"m8flow/tenants/{tenants[0]}/secrets/LEGACY_SECRET"
    fake_vault.storage[path] = {"value": "legacy-value"}

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        secret = backend.get_secret("LEGACY_SECRET")
        payload = backend.serialize_secret_list_result()

    assert secret.key == "LEGACY_SECRET"
    assert secret.to_dict()["user_id"] == 0
    assert payload["results"][0]["id"]
    assert payload["results"][0]["username"] is None


def test_update_upgrades_legacy_vault_document_with_metadata(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)
    path = f"m8flow/tenants/{tenants[0]}/secrets/LEGACY_SECRET"
    fake_vault.storage[path] = {"value": "legacy-value"}

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.update_secret("LEGACY_SECRET", "updated-value", user_id=user)

    assert fake_vault.storage[path]["value"] == "updated-value"
    assert fake_vault.storage[path]["user_id"] == user
    assert fake_vault.storage[path]["username"] == "alice"
    assert fake_vault.storage[path]["created_at_in_seconds"] is not None
    assert fake_vault.storage[path]["updated_at_in_seconds"] is not None


def test_get_secret_backend_uses_configured_storage_mode(app) -> None:
    with app.app_context():
        app.config["M8FLOW_SECRET_BACKEND_KIND"] = "legacy"
        assert isinstance(get_secret_backend(), LegacyDatabaseSecretBackend)
        assert isinstance(get_secret_backend(), SecretBackend)

        app.config["M8FLOW_SECRET_BACKEND_KIND"] = "vault"
        assert isinstance(get_secret_backend(), VaultBackedSecretBackend)
        assert isinstance(get_secret_backend(), SecretBackend)


def test_secret_backend_contract_accepts_current_backend_implementations(app) -> None:
    fake_vault = FakeVaultClient()

    with app.app_context():
        assert isinstance(LegacyDatabaseSecretBackend(), SecretBackend)
        assert isinstance(_backend(fake_vault), SecretBackend)


def test_secret_record_contract_accepts_resolved_secret() -> None:
    secret = ResolvedSecret(
        id="secret-1",
        key="API_TOKEN",
        user_id=7,
        value="enc:vault-value",
        updated_at_in_seconds=2,
        created_at_in_seconds=1,
        m8f_tenant_id="tenant-a",
    )

    assert isinstance(secret, SecretRecord)
