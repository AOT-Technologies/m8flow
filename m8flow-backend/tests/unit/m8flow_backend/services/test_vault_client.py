"""Unit tests for the Vault KV v2 wrapper."""
# ruff: noqa: E402
from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from flask import Flask

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"
for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.services import vault_client as vault_client_module
from m8flow_backend.services.vault_client import (
    VaultAppRoleSecretId,
    VaultAppRole,
    VaultClient,
    VaultConfigurationError,
    VaultConnectionError,
    VaultDependencyError,
    VaultOperationError,
    VaultSettings,
    VaultVersionConflictError,
)


class FakeInvalidPath(Exception):
    """Stand-in for hvac.exceptions.InvalidPath."""


class FakeForbidden(Exception):
    """Stand-in for hvac.exceptions.Forbidden."""


class FakeKvV2:
    def __init__(self) -> None:
        self.storage: dict[str, dict[str, object]] = {}
        self.create_calls: list[dict[str, object]] = []
        self.read_calls: list[dict[str, object]] = []
        self.list_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []
        self.read_exception: Exception | None = None
        self.list_exception: Exception | None = None
        self.write_exception: Exception | None = None
        self.delete_exception: Exception | None = None

    def create_or_update_secret(
        self,
        *,
        mount_point: str,
        path: str,
        secret: dict[str, object],
        cas: int | None = None,
    ) -> dict[str, object]:
        call = {"mount_point": mount_point, "path": path, "secret": secret}
        if cas is not None:
            call["cas"] = cas
        self.create_calls.append(call)
        if self.write_exception is not None:
            raise self.write_exception
        self.storage[path] = dict(secret)
        return {"data": {"path": path}}

    def read_secret_version(self, *, mount_point: str, path: str) -> dict[str, object]:
        self.read_calls.append({"mount_point": mount_point, "path": path})
        if self.read_exception is not None:
            raise self.read_exception
        if path not in self.storage:
            raise FakeInvalidPath(path)
        return {"data": {"data": dict(self.storage[path]), "metadata": {"version": 1}}}

    def list_secrets(self, *, mount_point: str, path: str) -> dict[str, object]:
        self.list_calls.append({"mount_point": mount_point, "path": path})
        if self.list_exception is not None:
            raise self.list_exception

        prefix = f"{path.strip('/')}/"
        keys: set[str] = set()
        for stored_path in self.storage:
            if not stored_path.startswith(prefix):
                continue
            remainder = stored_path[len(prefix) :]
            if not remainder:
                continue
            first_component, _separator, suffix = remainder.partition("/")
            keys.add(f"{first_component}/" if suffix else first_component)

        if not keys:
            raise FakeInvalidPath(path)

        return {"data": {"keys": sorted(keys)}}

    def delete_metadata_and_all_versions(self, *, mount_point: str, path: str) -> None:
        self.delete_calls.append({"mount_point": mount_point, "path": path})
        if self.delete_exception is not None:
            raise self.delete_exception
        if path not in self.storage:
            raise FakeInvalidPath(path)
        del self.storage[path]


class FakeSys:
    def __init__(self) -> None:
        self.health_calls: list[dict[str, object]] = []
        self.health_exception: Exception | None = None
        self.policy_calls: list[dict[str, str]] = []
        self.policy_exception: Exception | None = None
        self.policies: dict[str, str] = {}

    def read_health_status(self, **kwargs) -> dict[str, bool]:
        self.health_calls.append(kwargs)
        if self.health_exception is not None:
            raise self.health_exception
        return {"initialized": True}

    def create_or_update_policy(self, *, name: str, policy: str) -> None:
        self.policy_calls.append({"name": name, "policy": policy})
        if self.policy_exception is not None:
            raise self.policy_exception
        self.policies[name] = policy


class FakeAdapter:
    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.get_exception: Exception | None = None
        self.mount_response: dict[str, object] = {"data": {"options": {"version": "2"}}}

    def get(self, path: str) -> dict[str, object]:
        self.get_calls.append(path)
        if self.get_exception is not None:
            raise self.get_exception
        return self.mount_response


class FakeAppRoleAuth:
    def __init__(self, client: "FakeHvacClient") -> None:
        self.client = client
        self.login_calls: list[dict[str, str]] = []
        self.create_or_update_calls: list[dict[str, object]] = []
        self.read_role_id_calls: list[dict[str, str]] = []
        self.read_role_calls: list[dict[str, str]] = []
        self.generate_secret_id_calls: list[dict[str, str]] = []
        self.login_exception: Exception | None = None
        self.create_or_update_exception: Exception | None = None
        self.read_role_id_exception: Exception | None = None
        self.read_role_exception: Exception | None = None
        self.generate_secret_id_exception: Exception | None = None
        self.login_response: dict[str, object] | None = {"auth": {"client_token": "approle-token"}}
        self.create_or_update_response: dict[str, object] | None = {"data": {"created": True}}
        self.role_ids: dict[str, str] = {}
        self.roles: dict[str, dict[str, object]] = {}
        self.generate_secret_id_response: dict[str, object] | None = {
            "data": {
                "secret_id": "generated-secret-id",
                "secret_id_accessor": "generated-secret-id-accessor",
            }
        }

    def login(self, *, role_id: str, secret_id: str) -> dict[str, object] | None:
        self.login_calls.append({"role_id": role_id, "secret_id": secret_id})
        if self.login_exception is not None:
            raise self.login_exception
        return self.login_response

    def create_or_update_approle(
        self,
        *,
        role_name: str,
        mount_point: str,
        token_policies: list[str],
        bind_secret_id: bool,
        token_no_default_policy: bool,
        secret_id_num_uses: int | None = None,
        secret_id_ttl: str | int | None = None,
        token_ttl: str | int | None = None,
        token_max_ttl: str | int | None = None,
    ) -> dict[str, object] | None:
        self.create_or_update_calls.append(
            {
                "role_name": role_name,
                "mount_point": mount_point,
                "token_policies": token_policies,
                "bind_secret_id": bind_secret_id,
                "token_no_default_policy": token_no_default_policy,
                "secret_id_num_uses": secret_id_num_uses,
                "secret_id_ttl": secret_id_ttl,
                "token_ttl": token_ttl,
                "token_max_ttl": token_max_ttl,
            }
        )
        if self.create_or_update_exception is not None:
            raise self.create_or_update_exception
        self.role_ids.setdefault(role_name, f"role-id-for-{role_name}")
        self.roles[role_name] = {
            "token_policies": list(token_policies),
            "bind_secret_id": bind_secret_id,
            "token_no_default_policy": token_no_default_policy,
        }
        return self.create_or_update_response

    def read_role(self, *, role_name: str, mount_point: str) -> dict[str, object] | None:
        self.read_role_calls.append({"role_name": role_name, "mount_point": mount_point})
        if self.read_role_exception is not None:
            raise self.read_role_exception
        if role_name not in self.roles:
            raise FakeInvalidPath(role_name)
        return {"data": dict(self.roles[role_name])}

    def read_role_id(self, *, role_name: str, mount_point: str) -> dict[str, object] | None:
        self.read_role_id_calls.append({"role_name": role_name, "mount_point": mount_point})
        if self.read_role_id_exception is not None:
            raise self.read_role_id_exception
        return {"data": {"role_id": self.role_ids.get(role_name)}}

    def generate_secret_id(self, *, role_name: str, mount_point: str) -> dict[str, object] | None:
        self.generate_secret_id_calls.append({"role_name": role_name, "mount_point": mount_point})
        if self.generate_secret_id_exception is not None:
            raise self.generate_secret_id_exception
        return self.generate_secret_id_response


class FakeHvacClient:
    def __init__(self) -> None:
        self.kv_v2 = FakeKvV2()
        self.sys = FakeSys()
        self.adapter = FakeAdapter()
        self.secrets = SimpleNamespace(kv=SimpleNamespace(v2=self.kv_v2))
        self.auth = SimpleNamespace(approle=FakeAppRoleAuth(self))
        self.authenticated = True
        self.token: str | None = None

    def is_authenticated(self) -> bool:
        return self.authenticated


class FakeAuditLogService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.latest_event_calls: list[dict[str, object]] = []
        self.latest_event_response = None

    def try_record_event(self, **kwargs):
        self.calls.append(dict(kwargs))
        return kwargs

    def try_latest_event(self, **kwargs):
        self.latest_event_calls.append(dict(kwargs))
        return self.latest_event_response


def _settings(**overrides) -> VaultSettings:
    base = {
        "addr": "https://vault.example.com",
        "token": "vault-token",
        "role_id": None,
        "secret_id": None,
        "namespace": "engineering",
        "mount_point": "kv",
        "secret_path_prefix": "m8flow/test",
        "verify": True,
        "timeout_seconds": 5.0,
    }
    base.update(overrides)
    return VaultSettings(**base)


class TestVaultSettings:
    def test_from_env_reads_token_vault_configuration(self, monkeypatch):
        monkeypatch.setenv("M8FLOW_VAULT_ADDR", "https://vault.internal")
        monkeypatch.setenv("M8FLOW_VAULT_TOKEN", "token-123")
        monkeypatch.setenv("M8FLOW_VAULT_NAMESPACE", "platform/team-a")
        monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "secret-v2")
        monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow/custom")
        monkeypatch.setenv("M8FLOW_VAULT_TIMEOUT_SECONDS", "12.5")
        monkeypatch.setenv("M8FLOW_VAULT_SKIP_VERIFY", "true")

        settings = VaultSettings.from_env()

        assert settings.addr == "https://vault.internal"
        assert settings.token == "token-123"
        assert settings.role_id is None
        assert settings.secret_id is None
        assert settings.namespace == "platform/team-a"
        assert settings.mount_point == "secret-v2"
        assert settings.secret_path_prefix == "m8flow/custom"
        assert settings.timeout_seconds == 12.5
        assert settings.verify is False

    def test_from_env_reads_approle_credentials_from_files(self, monkeypatch, tmp_path):
        role_id_file = tmp_path / "role-id"
        secret_id_file = tmp_path / "secret-id"
        role_id_file.write_text("role-123\n", encoding="utf-8")
        secret_id_file.write_text("secret-456\n", encoding="utf-8")
        monkeypatch.setenv("M8FLOW_VAULT_ADDR", "https://vault.internal")
        monkeypatch.delenv("M8FLOW_VAULT_TOKEN", raising=False)
        monkeypatch.setenv("M8FLOW_VAULT_ROLE_ID_FILE", str(role_id_file))
        monkeypatch.setenv("M8FLOW_VAULT_SECRET_ID_FILE", str(secret_id_file))

        settings = VaultSettings.from_env()

        assert settings.token is None
        assert settings.role_id == "role-123"
        assert settings.secret_id == "secret-456"
        assert settings.auth_method == "approle"
        assert settings.is_configured is True

    def test_from_env_decrypts_encrypted_demo_approle_credentials_from_files(self, monkeypatch, tmp_path):
        state_key = "0123456789abcdef0123456789abcdef"
        digest = hashlib.sha256(state_key.encode("utf-8")).digest()
        cipher = Fernet(base64.urlsafe_b64encode(digest))
        prefix = "m8flow-vault-demo:enc:v1:"

        role_id_file = tmp_path / "role-id"
        secret_id_file = tmp_path / "secret-id"
        role_id_file.write_text(prefix + cipher.encrypt(b"role-123\n").decode("utf-8") + "\n", encoding="utf-8")
        secret_id_file.write_text(prefix + cipher.encrypt(b"secret-456\n").decode("utf-8") + "\n", encoding="utf-8")
        monkeypatch.setenv("M8FLOW_BACKEND_ENCRYPTION_KEY", state_key)
        monkeypatch.setenv("M8FLOW_VAULT_ADDR", "https://vault.internal")
        monkeypatch.delenv("M8FLOW_VAULT_TOKEN", raising=False)
        monkeypatch.setenv("M8FLOW_VAULT_ROLE_ID_FILE", str(role_id_file))
        monkeypatch.setenv("M8FLOW_VAULT_SECRET_ID_FILE", str(secret_id_file))

        settings = VaultSettings.from_env()

        assert settings.token is None
        assert settings.role_id == "role-123"
        assert settings.secret_id == "secret-456"
        assert settings.auth_method == "approle"
        assert settings.is_configured is True

    def test_with_approle_credentials_reuses_connection_details_and_clears_token(self):
        settings = _settings(token="shared-token", role_id=None, secret_id=None)

        tenant_settings = settings.with_approle_credentials(
            role_id="tenant-role-id",
            secret_id="tenant-secret-id",
        )

        assert tenant_settings.addr == settings.addr
        assert tenant_settings.token is None
        assert tenant_settings.role_id == "tenant-role-id"
        assert tenant_settings.secret_id == "tenant-secret-id"
        assert tenant_settings.namespace == settings.namespace
        assert tenant_settings.mount_point == settings.mount_point
        assert tenant_settings.secret_path_prefix == settings.secret_path_prefix


class TestVaultClientOperations:
    def test_read_approle_returns_role_payload(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        fake_client.auth.approle.roles["tenant-role"] = {"token_policies": ["tenant-policy"]}
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        role = client.read_approle("tenant-role", mount_point="approle-custom")

        assert role == VaultAppRole(data={"token_policies": ["tenant-policy"]})
        assert fake_client.auth.approle.read_role_calls == [
            {"role_name": "tenant-role", "mount_point": "approle-custom"}
        ]

    def test_read_approle_returns_none_for_missing_role(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        role = client.read_approle("tenant-role", mount_point="approle-custom")

        assert role is None

    def test_create_or_update_policy_writes_policy_document(self):
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        client.create_or_update_policy("tenant-policy", 'path "kv/data/m8flow/*" {}')

        assert fake_client.sys.policy_calls == [
            {"name": "tenant-policy", "policy": 'path "kv/data/m8flow/*" {}'}
        ]
        assert fake_client.sys.policies["tenant-policy"] == 'path "kv/data/m8flow/*" {}'

    def test_create_or_update_approle_writes_role_configuration(self):
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        result = client.create_or_update_approle(
            "tenant-role",
            mount_point="approle-custom",
            token_policies=["tenant-policy"],
            secret_id_num_uses=1,
            secret_id_ttl="10m",
            token_ttl="10m",
            token_max_ttl="30m",
        )

        assert result == {"data": {"created": True}}
        assert fake_client.auth.approle.create_or_update_calls == [
            {
                "role_name": "tenant-role",
                "mount_point": "approle-custom",
                "token_policies": ["tenant-policy"],
                "bind_secret_id": True,
                "token_no_default_policy": True,
                "secret_id_num_uses": 1,
                "secret_id_ttl": "10m",
                "token_ttl": "10m",
                "token_max_ttl": "30m",
            }
        ]

    def test_read_approle_role_id_returns_role_id(self):
        fake_client = FakeHvacClient()
        fake_client.auth.approle.role_ids["tenant-role"] = "role-id-123"
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        role_id = client.read_approle_role_id("tenant-role", mount_point="approle-custom")

        assert role_id == "role-id-123"
        assert fake_client.auth.approle.read_role_id_calls == [
            {"role_name": "tenant-role", "mount_point": "approle-custom"}
        ]

    def test_generate_approle_secret_id_returns_secret_and_accessor(self):
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        secret_id = client.generate_approle_secret_id("tenant-role", mount_point="approle-custom")

        assert secret_id == VaultAppRoleSecretId(
            secret_id="generated-secret-id",
            secret_id_accessor="generated-secret-id-accessor",
        )
        assert fake_client.auth.approle.generate_secret_id_calls == [
            {"role_name": "tenant-role", "mount_point": "approle-custom"}
        ]

    def test_store_secret_document_writes_full_payload_under_prefixed_path(self):
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        result = client.store_secret_document(
            "SMTP_PASSWORD",
            {
                "value": "super-secret",
                "tenant_id": "tenant-123",
                "updated_by": "admin",
            },
        )

        assert result == {"data": {"path": "m8flow/test/SMTP_PASSWORD"}}
        assert fake_client.kv_v2.create_calls == [
            {
                "mount_point": "kv",
                "path": "m8flow/test/SMTP_PASSWORD",
                "secret": {
                    "value": "super-secret",
                    "tenant_id": "tenant-123",
                    "updated_by": "admin",
                },
            }
        ]

    def test_store_secret_writes_string_value_under_prefixed_path(self):
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        result = client.store_secret("SMTP_PASSWORD", "super-secret")

        assert result == {"data": {"path": "m8flow/test/SMTP_PASSWORD"}}
        assert fake_client.kv_v2.create_calls == [
            {
                "mount_point": "kv",
                "path": "m8flow/test/SMTP_PASSWORD",
                "secret": {"value": "super-secret"},
            }
        ]

    def test_store_secret_document_passes_expected_version_as_kv_cas(self):
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        client.store_secret_document("connector-document", {"token": "secret"}, "3")

        assert fake_client.kv_v2.create_calls == [
            {
                "mount_point": "kv",
                "path": "m8flow/test/connector-document",
                "secret": {"token": "secret"},
                "cas": 3,
            }
        ]

    def test_store_secret_does_not_double_prefix_already_qualified_path(self):
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        result = client.store_secret(
            "m8flow/test/tenants/tenant-1/secrets/SMTP_PASSWORD",
            "super-secret",
        )

        assert result == {"data": {"path": "m8flow/test/tenants/tenant-1/secrets/SMTP_PASSWORD"}}
        assert fake_client.kv_v2.create_calls == [
            {
                "mount_point": "kv",
                "path": "m8flow/test/tenants/tenant-1/secrets/SMTP_PASSWORD",
                "secret": {"value": "super-secret"},
            }
        ]

    def test_retrieve_secret_document_returns_full_payload(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        fake_client.kv_v2.storage["m8flow/test/SMTP_PASSWORD"] = {
            "value": "super-secret",
            "tenant_id": "tenant-123",
            "updated_by": "admin",
        }
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        value = client.retrieve_secret_document("SMTP_PASSWORD")

        assert value == {
            "value": "super-secret",
            "tenant_id": "tenant-123",
            "updated_by": "admin",
        }
        assert fake_client.kv_v2.read_calls == [
            {"mount_point": "kv", "path": "m8flow/test/SMTP_PASSWORD"}
        ]

    def test_retrieve_secret_document_with_version_returns_kv_version(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        fake_client.kv_v2.storage["m8flow/test/SMTP_PASSWORD"] = {"value": "secret"}
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        assert client.retrieve_secret_document_with_version("SMTP_PASSWORD") == (
            {"value": "secret"},
            "1",
        )

    def test_store_secret_document_maps_cas_mismatch_to_version_conflict(self):
        fake_client = FakeHvacClient()
        fake_client.kv_v2.write_exception = RuntimeError(
            "check-and-set parameter did not match the current version"
        )
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        with pytest.raises(VaultVersionConflictError, match="changed before"):
            client.store_secret_document("SMTP_PASSWORD", {"value": "secret"}, "1")

    def test_retrieve_secret_returns_string_value(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        fake_client.kv_v2.storage["m8flow/test/SMTP_PASSWORD"] = {"value": "super-secret"}
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        value = client.retrieve_secret("SMTP_PASSWORD")

        assert value == "super-secret"
        assert fake_client.kv_v2.read_calls == [
            {"mount_point": "kv", "path": "m8flow/test/SMTP_PASSWORD"}
        ]

    def test_retrieve_secret_does_not_double_prefix_already_qualified_path(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        fake_client.kv_v2.storage["m8flow/test/tenants/tenant-1/secrets/SMTP_PASSWORD"] = {
            "value": "super-secret"
        }
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        value = client.retrieve_secret("m8flow/test/tenants/tenant-1/secrets/SMTP_PASSWORD")

        assert value == "super-secret"
        assert fake_client.kv_v2.read_calls == [
            {
                "mount_point": "kv",
                "path": "m8flow/test/tenants/tenant-1/secrets/SMTP_PASSWORD",
            }
        ]

    def test_retrieve_secret_returns_none_for_missing_path(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        assert client.retrieve_secret("MISSING_SECRET") is None

    def test_list_secret_names_returns_direct_children_for_prefix(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        fake_client.kv_v2.storage["m8flow/test/tenants/tenant-1/secrets/API_TOKEN"] = {"value": "one"}
        fake_client.kv_v2.storage["m8flow/test/tenants/tenant-1/secrets/SMTP_PASSWORD"] = {"value": "two"}
        fake_client.kv_v2.storage["m8flow/test/tenants/tenant-2/secrets/API_TOKEN"] = {"value": "three"}
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        result = client.list_secret_names("m8flow/test/tenants/tenant-1/secrets")

        assert result == ["API_TOKEN", "SMTP_PASSWORD"]
        assert fake_client.kv_v2.list_calls == [
            {"mount_point": "kv", "path": "m8flow/test/tenants/tenant-1/secrets"}
        ]

    def test_list_secret_names_returns_none_for_missing_prefix(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        result = client.list_secret_names("m8flow/test/tenants/tenant-1/secrets")

        assert result == []

    def test_delete_secret_returns_true_for_existing_secret(self, monkeypatch):
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(InvalidPath=FakeInvalidPath),
        )
        fake_client = FakeHvacClient()
        fake_client.kv_v2.storage["m8flow/test/SMTP_PASSWORD"] = {"value": "super-secret"}
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        deleted = client.delete_secret("SMTP_PASSWORD")

        assert deleted is True
        assert fake_client.kv_v2.delete_calls == [
            {"mount_point": "kv", "path": "m8flow/test/SMTP_PASSWORD"}
        ]
        assert "m8flow/test/SMTP_PASSWORD" not in fake_client.kv_v2.storage

    def test_store_secret_raises_graceful_connection_error(self):
        fake_client = FakeHvacClient()
        fake_client.kv_v2.write_exception = OSError("connection refused")
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        with pytest.raises(VaultConnectionError, match="Vault is unreachable"):
            client.store_secret("SMTP_PASSWORD", "super-secret")

    def test_check_availability_returns_true_for_healthy_authenticated_client(self):
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        available = client.check_availability()

        assert available is True
        assert fake_client.sys.health_calls == [
            {"method": "GET", "standby_ok": True, "performance_standby_code": 200}
        ]

    def test_check_availability_records_success_audit_event(self):
        fake_client = FakeHvacClient()
        fake_audit = FakeAuditLogService()
        client = VaultClient(
            settings=_settings(),
            client_factory=lambda _settings: fake_client,
            audit_log_service=fake_audit,
        )
        app = Flask(__name__)

        with app.app_context():
            available = client.check_availability()

        assert available is True
        assert fake_audit.calls == [
            {
                "category": "vault",
                "event_type": "vault.health.check",
                "source": "vault_client",
                "status": "success",
                "severity": "info",
                "message": "Vault availability check succeeded.",
                "details": {
                    "configured": True,
                    "authenticated": True,
                    "mount_point": "kv",
                    "auth_method": "token",
                },
            }
        ]

    def test_check_availability_records_failed_audit_event_without_leaking_exception_text(self, caplog):
        fake_client = FakeHvacClient()
        fake_client.sys.health_exception = OSError("token=secret-123")
        fake_audit = FakeAuditLogService()
        client = VaultClient(
            settings=_settings(),
            client_factory=lambda _settings: fake_client,
            audit_log_service=fake_audit,
        )
        app = Flask(__name__)

        with caplog.at_level("WARNING", logger="m8flow.vault.client"):
            with app.app_context():
                available = client.check_availability()

        assert available is False
        assert "token=secret-123" not in caplog.text
        assert fake_audit.calls == [
            {
                "category": "vault",
                "event_type": "vault.health.check",
                "source": "vault_client",
                "status": "failed",
                "severity": "error",
                "message": "Vault availability check failed.",
                "details": {
                    "configured": True,
                    "mount_point": "kv",
                    "auth_method": "token",
                    "error_type": "OSError",
                },
            }
        ]
        assert "token=secret-123" not in repr(fake_audit.calls[0])

    def test_check_availability_transition_audit_records_initial_observation(self):
        fake_client = FakeHvacClient()
        fake_audit = FakeAuditLogService()
        client = VaultClient(
            settings=_settings(),
            client_factory=lambda _settings: fake_client,
            audit_log_service=fake_audit,
        )
        app = Flask(__name__)

        with app.app_context():
            available = client.check_availability(transitions_only=True)

        assert available is True
        assert fake_audit.latest_event_calls == [
            {
                "category": "vault",
                "event_type": "vault.health.check",
                "source": "vault_client",
            }
        ]
        assert fake_audit.calls == [
            {
                "category": "vault",
                "event_type": "vault.health.check",
                "source": "vault_client",
                "status": "success",
                "severity": "info",
                "message": "Vault availability check succeeded.",
                "details": {
                    "configured": True,
                    "authenticated": True,
                    "mount_point": "kv",
                    "auth_method": "token",
                },
            }
        ]

    def test_check_availability_transition_audit_skips_duplicate_status(self):
        fake_client = FakeHvacClient()
        fake_audit = FakeAuditLogService()
        fake_audit.latest_event_response = SimpleNamespace(status="success")
        client = VaultClient(
            settings=_settings(),
            client_factory=lambda _settings: fake_client,
            audit_log_service=fake_audit,
        )
        app = Flask(__name__)

        with app.app_context():
            available = client.check_availability(transitions_only=True)

        assert available is True
        assert fake_audit.latest_event_calls == [
            {
                "category": "vault",
                "event_type": "vault.health.check",
                "source": "vault_client",
            }
        ]
        assert fake_audit.calls == []

    def test_check_availability_transition_audit_records_status_change(self):
        fake_client = FakeHvacClient()
        fake_client.sys.health_exception = OSError("connection refused")
        fake_audit = FakeAuditLogService()
        fake_audit.latest_event_response = SimpleNamespace(status="success")
        client = VaultClient(
            settings=_settings(),
            client_factory=lambda _settings: fake_client,
            audit_log_service=fake_audit,
        )
        app = Flask(__name__)

        with app.app_context():
            available = client.check_availability(transitions_only=True)

        assert available is False
        assert fake_audit.latest_event_calls == [
            {
                "category": "vault",
                "event_type": "vault.health.check",
                "source": "vault_client",
            }
        ]
        assert fake_audit.calls == [
            {
                "category": "vault",
                "event_type": "vault.health.check",
                "source": "vault_client",
                "status": "failed",
                "severity": "error",
                "message": "Vault availability check failed.",
                "details": {
                    "configured": True,
                    "mount_point": "kv",
                    "auth_method": "token",
                    "error_type": "OSError",
                },
            }
        ]

    def test_assert_startup_ready_uses_mount_metadata_endpoint(self):
        fake_client = FakeHvacClient()
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        client.assert_startup_ready()

        assert fake_client.sys.health_calls == [
            {"method": "GET", "standby_ok": True, "performance_standby_code": 200}
        ]
        assert fake_client.adapter.get_calls == ["/v1/sys/internal/ui/mounts/kv"]

    def test_assert_startup_ready_raises_when_mount_is_not_kv_v2(self):
        fake_client = FakeHvacClient()
        fake_client.adapter.mount_response = {"data": {"options": {"version": "1"}}}
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        with pytest.raises(VaultOperationError, match="not configured as KV v2"):
            client.assert_startup_ready()

    def test_assert_startup_ready_raises_when_mount_metadata_is_unavailable(self):
        fake_client = FakeHvacClient()
        fake_client.adapter.mount_response = {"data": None}
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        with pytest.raises(VaultOperationError, match="is unavailable"):
            client.assert_startup_ready()

    def test_assert_startup_ready_skips_mount_metadata_when_preflight_is_forbidden(self, monkeypatch, caplog):
        fake_client = FakeHvacClient()
        fake_client.adapter.get_exception = FakeForbidden(
            'preflight capability check returned 403, please ensure client\'s policies grant access '
            'to path "kv/", on get http://vault:8200/v1/sys/internal/ui/mounts/kv'
        )
        monkeypatch.setattr(
            vault_client_module,
            "hvac_exceptions",
            SimpleNamespace(
                InvalidPath=FakeInvalidPath,
                Forbidden=FakeForbidden,
            ),
        )
        client = VaultClient(settings=_settings(), client_factory=lambda _settings: fake_client)

        with caplog.at_level("INFO", logger="m8flow.vault.client"):
            client.assert_startup_ready()

        assert fake_client.adapter.get_calls == ["/v1/sys/internal/ui/mounts/kv"]
        assert "skipping mount metadata validation" in caplog.text.lower()

    def test_check_availability_returns_false_when_not_configured(self):
        client = VaultClient(
            settings=_settings(addr=None, token=None, role_id=None, secret_id=None),
            client_factory=lambda _settings: pytest.fail("client factory should not be called"),
        )

        assert client.check_availability() is False

    def test_approle_authenticates_before_first_operation(self, monkeypatch):
        fake_client = FakeHvacClient()
        monkeypatch.setattr(
            vault_client_module,
            "hvac",
            SimpleNamespace(Client=lambda **_kwargs: fake_client),
        )
        client = VaultClient(
            settings=_settings(token=None, role_id="role-123", secret_id="secret-456"),
        )

        result = client.store_secret("SMTP_PASSWORD", "super-secret")

        assert result == {"data": {"path": "m8flow/test/SMTP_PASSWORD"}}
        assert fake_client.auth.approle.login_calls == [
            {"role_id": "role-123", "secret_id": "secret-456"}
        ]
        assert fake_client.token == "approle-token"

    def test_missing_auth_configuration_raises_configuration_error(self):
        client = VaultClient(
            settings=_settings(token=None, role_id=None, secret_id=None),
            client_factory=lambda _settings: pytest.fail("client factory should not be called"),
        )

        with pytest.raises(VaultConfigurationError, match="M8FLOW_VAULT_ADDR"):
            client.store_secret("SMTP_PASSWORD", "super-secret")

    def test_approle_login_without_client_token_raises_operation_error(self, monkeypatch):
        fake_client = FakeHvacClient()
        fake_client.auth.approle.login_response = {"auth": {}}
        monkeypatch.setattr(
            vault_client_module,
            "hvac",
            SimpleNamespace(Client=lambda **_kwargs: fake_client),
        )
        client = VaultClient(
            settings=_settings(token=None, role_id="role-123", secret_id="secret-456"),
        )

        with pytest.raises(VaultOperationError, match="did not return a client token"):
            client.store_secret("SMTP_PASSWORD", "super-secret")

    def test_missing_hvac_dependency_raises_dependency_error(self, monkeypatch):
        monkeypatch.setattr(vault_client_module, "hvac", None)
        client = VaultClient(settings=_settings())

        with pytest.raises(VaultDependencyError, match="hvac"):
            client.store_secret("SMTP_PASSWORD", "super-secret")
