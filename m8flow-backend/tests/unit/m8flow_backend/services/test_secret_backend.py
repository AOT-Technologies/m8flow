from __future__ import annotations
# ruff: noqa: E402

import sys
from pathlib import Path

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
from m8flow_backend.models.vault_metadata import VaultMetadataModel
from m8flow_backend.services.secret_backend import (
    LegacyDatabaseSecretBackend,
    VaultBackedSecretBackend,
    get_secret_backend,
)
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
        self.storage: dict[str, str] = {}
        self.store_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []
        self.retrieve_calls: list[str] = []
        self.fail_store: Exception | None = None
        self.fail_delete: Exception | None = None
        self.fail_retrieve: Exception | None = None

    def store_secret(self, path: str, value: str) -> dict[str, object]:
        self.store_calls.append((path, value))
        if self.fail_store is not None:
            raise self.fail_store
        self.storage[path] = value
        return {"data": {"path": path}}

    def retrieve_secret(self, path: str) -> str | None:
        self.retrieve_calls.append(path)
        if self.fail_retrieve is not None:
            raise self.fail_retrieve
        return self.storage.get(path)

    def delete_secret(self, path: str) -> bool:
        self.delete_calls.append(path)
        if self.fail_delete is not None:
            raise self.fail_delete
        existed = path in self.storage
        self.storage.pop(path, None)
        return existed


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


def _backend(fake_vault: FakeVaultClient) -> VaultBackedSecretBackend:
    return VaultBackedSecretBackend(vault_client=fake_vault)


def test_vault_mode_create_persists_metadata_only_and_stores_value(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()

    with app.app_context():
        with app.test_request_context("/"):
            g.m8flow_tenant_id = tenants[0]
            secret = _backend(fake_vault).add_secret("SMTP_PASSWORD", "super-secret", user)

        metadata = VaultMetadataModel.query.one()
        expected_path = f"m8flow/tenants/{tenants[0]}/secrets/SMTP_PASSWORD"

        assert metadata.name == "SMTP_PASSWORD"
        assert "value" not in VaultMetadataModel.__table__.columns
        assert fake_vault.storage[expected_path] == "super-secret"
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
            assert fake_vault.storage[f"m8flow/tenants/{tenants[0]}/secrets/SHARED_KEY"] == "tenant-a-value"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = tenants[1]
            backend.add_secret("SHARED_KEY", "tenant-b-value", user)

        assert VaultMetadataModel.query.count() == 2


def test_tenant_a_cannot_resolve_tenant_b_metadata(app, tenants, user) -> None:
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
        backend.add_secret("OLD_NAME", "initial", user)
        original_path = f"m8flow/tenants/{tenants[0]}/secrets/OLD_NAME"
        renamed_path = f"m8flow/tenants/{tenants[0]}/secrets/NEW_NAME"

        backend.update_secret("OLD_NAME", "updated", user, new_key="NEW_NAME")
        resolved = backend.get_secret("NEW_NAME")
        with pytest.raises(ApiError):
            backend.get_secret("OLD_NAME")

    assert fake_vault.store_calls[0][0] == original_path
    assert fake_vault.store_calls[-1][0] == renamed_path
    assert fake_vault.delete_calls[-1] == original_path
    assert fake_vault.storage[renamed_path] == "updated"
    assert resolved.key == "NEW_NAME"


def test_rename_to_existing_secret_is_rejected_before_touching_vault(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("OLD_NAME", "initial", user)
        backend.add_secret("EXISTING_NAME", "existing", user)

        with pytest.raises(ApiError) as exc_info:
            backend.update_secret("OLD_NAME", "updated", user, new_key="EXISTING_NAME")

    assert exc_info.value.error_code == "update_secret_error"
    assert fake_vault.storage[f"m8flow/tenants/{tenants[0]}/secrets/OLD_NAME"] == "initial"
    assert fake_vault.storage[f"m8flow/tenants/{tenants[0]}/secrets/EXISTING_NAME"] == "existing"


def test_metadata_creation_failure_triggers_compensating_vault_delete(app, tenants, user, monkeypatch) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        monkeypatch.setattr(db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("db failed")))
        with pytest.raises(ApiError) as exc_info:
            backend.add_secret("BROKEN_CREATE", "secret", user)

    assert exc_info.value.error_code == "create_secret_error"
    assert len(fake_vault.store_calls) == 1
    assert fake_vault.delete_calls == [fake_vault.store_calls[0][0]]


def test_missing_vault_value_with_present_metadata_is_returned_as_not_found(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("API_TOKEN", "vault-value", user)
        fake_vault.storage.clear()
        with pytest.raises(ApiError) as exc_info:
            backend.get_secret("API_TOKEN")

    assert exc_info.value.error_code == "vault_secret_value_missing"
    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Unable to locate the Vault secret value for key: API_TOKEN."


def test_delete_removes_vault_value_and_metadata_and_tolerates_missing_vault_value(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.app_context():
        with app.test_request_context("/"):
            g.m8flow_tenant_id = tenants[0]
            backend.add_secret("API_TOKEN", "vault-value", user)
            backend.delete_secret("API_TOKEN", user)
            assert VaultMetadataModel.query.count() == 0

            backend.add_secret("API_TOKEN", "vault-value", user)
            fake_vault.storage.clear()
            backend.delete_secret("API_TOKEN", user)

        assert VaultMetadataModel.query.count() == 0


def test_list_responses_do_not_include_secret_values(app, tenants, user) -> None:
    fake_vault = FakeVaultClient()
    backend = _backend(fake_vault)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = tenants[0]
        backend.add_secret("API_TOKEN", "vault-value", user)
        payload = backend.serialize_secret_list_result()

    assert payload["results"][0]["key"] == "API_TOKEN"
    assert "value" not in payload["results"][0]


def test_get_secret_backend_uses_configured_storage_mode(app) -> None:
    with app.app_context():
        app.config["M8FLOW_SECRET_BACKEND_KIND"] = "legacy"
        assert isinstance(get_secret_backend(), LegacyDatabaseSecretBackend)
