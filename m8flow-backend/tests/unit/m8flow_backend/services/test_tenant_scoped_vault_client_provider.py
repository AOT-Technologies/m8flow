from __future__ import annotations

import sys
from pathlib import Path

import pytest

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"
for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.services.tenant_scoped_vault_client_provider import (  # noqa: E402
    TenantScopedVaultClient,
    TenantScopedVaultClientError,
    TenantScopedVaultClientProvider,
)
from m8flow_backend.services.vault_client import (  # noqa: E402
    VaultAppRole,
    VaultAppRoleSecretId,
    VaultOperationError,
    VaultSettings,
)


class FakeBrokerVaultClient:
    def __init__(self) -> None:
        self.settings = VaultSettings(
            addr="https://vault.example.com",
            token="shared-runtime-token",
            role_id=None,
            secret_id=None,
            namespace="engineering",
            mount_point="kv",
            secret_path_prefix="m8flow",
            verify=True,
            timeout_seconds=5.0,
        )
        self.read_approle_calls: list[dict[str, str]] = []
        self.read_approle_role_id_calls: list[dict[str, str]] = []
        self.generate_secret_id_calls: list[dict[str, str]] = []
        self.roles: dict[str, VaultAppRole] = {}
        self.role_ids: dict[str, str] = {}
        self.secret_ids: dict[str, VaultAppRoleSecretId] = {}
        self.read_role_id_error: Exception | None = None

    def read_approle(self, role_name: str, *, mount_point: str) -> VaultAppRole | None:
        self.read_approle_calls.append({"role_name": role_name, "mount_point": mount_point})
        return self.roles.get(role_name)

    def read_approle_role_id(self, role_name: str, *, mount_point: str) -> str:
        self.read_approle_role_id_calls.append({"role_name": role_name, "mount_point": mount_point})
        if self.read_role_id_error is not None:
            raise self.read_role_id_error
        return self.role_ids[role_name]

    def generate_approle_secret_id(self, role_name: str, *, mount_point: str) -> VaultAppRoleSecretId:
        self.generate_secret_id_calls.append({"role_name": role_name, "mount_point": mount_point})
        return self.secret_ids[role_name]


def test_provider_builds_tenant_scoped_client_from_tenant_approle(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")

    broker_client = FakeBrokerVaultClient()
    role_name = "m8flow-tenant-role-org-uuid-123"
    broker_client.roles[role_name] = VaultAppRole(data={"token_policies": ["m8flow-tenant-policy-org-uuid-123"]})
    broker_client.role_ids[role_name] = "tenant-role-id-123"
    broker_client.secret_ids[role_name] = VaultAppRoleSecretId(
        secret_id="tenant-secret-id-123",
        secret_id_accessor="tenant-secret-id-accessor-123",
    )
    built_settings: list[VaultSettings] = []
    tenant_vault_client = object()

    def _build_tenant_client(settings: VaultSettings):
        built_settings.append(settings)
        return tenant_vault_client

    provider = TenantScopedVaultClientProvider(
        broker_vault_client=broker_client,
        vault_client_builder=_build_tenant_client,
    )

    scoped_client = provider.for_tenant("org-uuid-123")

    assert scoped_client == TenantScopedVaultClient(
        tenant_id="org-uuid-123",
        role_name=role_name,
        role_id="tenant-role-id-123",
        secret_id_accessor="tenant-secret-id-accessor-123",
        vault_client=tenant_vault_client,
    )
    assert built_settings == [
        VaultSettings(
            addr="https://vault.example.com",
            token=None,
            role_id="tenant-role-id-123",
            secret_id="tenant-secret-id-123",
            namespace="engineering",
            mount_point="kv",
            secret_path_prefix="m8flow",
            verify=True,
            timeout_seconds=5.0,
        )
    ]


def test_provider_raises_when_tenant_approle_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")

    provider = TenantScopedVaultClientProvider(
        broker_vault_client=FakeBrokerVaultClient(),
        vault_client_builder=lambda settings: settings,
    )

    with pytest.raises(TenantScopedVaultClientError, match="does not exist"):
        provider.for_tenant("org-uuid-123")


def test_provider_wraps_broker_vault_errors(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")

    broker_client = FakeBrokerVaultClient()
    role_name = "m8flow-tenant-role-org-uuid-123"
    broker_client.roles[role_name] = VaultAppRole(data={"token_policies": ["tenant-policy"]})
    broker_client.read_role_id_error = VaultOperationError("role-id lookup failed")

    provider = TenantScopedVaultClientProvider(
        broker_vault_client=broker_client,
        vault_client_builder=lambda settings: settings,
    )

    with pytest.raises(TenantScopedVaultClientError, match="Could not resolve"):
        provider.for_tenant("org-uuid-123")
