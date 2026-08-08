"""Unit tests for the Vault KV v2 wrapper."""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    VaultClient,
    VaultConfigurationError,
    VaultConnectionError,
    VaultDependencyError,
    VaultOperationError,
    VaultSettings,
)


class FakeInvalidPath(Exception):
    """Stand-in for hvac.exceptions.InvalidPath."""


class FakeKvV2:
    def __init__(self) -> None:
        self.storage: dict[str, dict[str, str]] = {}
        self.create_calls: list[dict[str, object]] = []
        self.read_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []
        self.read_exception: Exception | None = None
        self.write_exception: Exception | None = None
        self.delete_exception: Exception | None = None

    def create_or_update_secret(self, *, mount_point: str, path: str, secret: dict[str, str]) -> dict[str, object]:
        self.create_calls.append({"mount_point": mount_point, "path": path, "secret": secret})
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
        return {"data": {"data": dict(self.storage[path])}}

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

    def read_health_status(self, **kwargs) -> dict[str, bool]:
        self.health_calls.append(kwargs)
        if self.health_exception is not None:
            raise self.health_exception
        return {"initialized": True}


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
        self.login_exception: Exception | None = None
        self.login_response: dict[str, object] | None = {"auth": {"client_token": "approle-token"}}

    def login(self, *, role_id: str, secret_id: str) -> dict[str, object] | None:
        self.login_calls.append({"role_id": role_id, "secret_id": secret_id})
        if self.login_exception is not None:
            raise self.login_exception
        return self.login_response


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


class TestVaultClientOperations:
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
