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

from m8flow_backend.services.tenant_vault_provisioning_service import (  # noqa: E402
    TenantVaultIdentity,
    TenantVaultProvisioningService,
)
from m8flow_backend.services.vault_client import VaultAppRoleSecretId, VaultSettings  # noqa: E402


class FakeTenantProvisioningVaultClient:
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
        self.policy_calls: list[dict[str, str]] = []
        self.approle_calls: list[dict[str, object]] = []
        self.read_approle_calls: list[dict[str, str]] = []
        self.role_id_calls: list[dict[str, str]] = []
        self.secret_id_calls: list[dict[str, str]] = []
        self.roles: dict[str, dict[str, object]] = {}

    def read_approle(self, role_name: str, *, mount_point: str):
        self.read_approle_calls.append({"role_name": role_name, "mount_point": mount_point})
        payload = self.roles.get(role_name)
        if payload is None:
            return None
        return {"data": payload}

    def create_or_update_policy(self, policy_name: str, policy: str) -> None:
        self.policy_calls.append({"policy_name": policy_name, "policy": policy})

    def create_or_update_approle(
        self,
        role_name: str,
        *,
        token_policies: list[str],
        mount_point: str,
        token_no_default_policy: bool = True,
    ) -> dict[str, object]:
        self.approle_calls.append(
            {
                "role_name": role_name,
                "token_policies": token_policies,
                "mount_point": mount_point,
                "token_no_default_policy": token_no_default_policy,
            }
        )
        self.roles[role_name] = {"token_policies": list(token_policies)}
        return {"data": {"created": True}}

    def read_approle_role_id(self, role_name: str, *, mount_point: str) -> str:
        self.role_id_calls.append({"role_name": role_name, "mount_point": mount_point})
        return f"role-id-for-{role_name}"

    def generate_approle_secret_id(self, role_name: str, *, mount_point: str) -> VaultAppRoleSecretId:
        self.secret_id_calls.append({"role_name": role_name, "mount_point": mount_point})
        return VaultAppRoleSecretId(
            secret_id=f"secret-id-for-{role_name}",
            secret_id_accessor=f"accessor-for-{role_name}",
        )


def test_provision_tenant_identity_creates_policy_and_approle(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")

    fake_vault_client = FakeTenantProvisioningVaultClient()
    service = TenantVaultProvisioningService(vault_client=fake_vault_client)

    result = service.provision_tenant_identity("org-uuid-123")

    assert result == TenantVaultIdentity(
        tenant_id="org-uuid-123",
        policy_name="m8flow-tenant-policy-org-uuid-123",
        role_name="m8flow-tenant-role-org-uuid-123",
        role_id="role-id-for-m8flow-tenant-role-org-uuid-123",
        secret_id="secret-id-for-m8flow-tenant-role-org-uuid-123",
        secret_id_accessor="accessor-for-m8flow-tenant-role-org-uuid-123",
        created_new_secret_id=True,
    )
    assert fake_vault_client.policy_calls == [
        {
            "policy_name": "m8flow-tenant-policy-org-uuid-123",
            "policy": (
                'path "kv/data/m8flow/tenants/org-uuid-123/secrets/*" {\n'
                '  capabilities = ["create", "read", "update", "delete"]\n'
                "}\n\n"
                'path "kv/metadata/m8flow/tenants/org-uuid-123/secrets" {\n'
                '  capabilities = ["list", "read"]\n'
                "}\n\n"
                'path "kv/metadata/m8flow/tenants/org-uuid-123/secrets/*" {\n'
                '  capabilities = ["list", "read", "delete"]\n'
                "}\n"
            ),
        }
    ]
    assert fake_vault_client.approle_calls == [
        {
            "role_name": "m8flow-tenant-role-org-uuid-123",
            "token_policies": ["m8flow-tenant-policy-org-uuid-123"],
            "mount_point": "approle",
            "token_no_default_policy": True,
        }
    ]
    assert fake_vault_client.secret_id_calls == [
        {
            "role_name": "m8flow-tenant-role-org-uuid-123",
            "mount_point": "approle",
        }
    ]


def test_provision_tenant_identity_does_not_rotate_secret_for_existing_role(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")

    fake_vault_client = FakeTenantProvisioningVaultClient()
    fake_vault_client.roles["m8flow-tenant-role-org-uuid-123"] = {
        "token_policies": ["m8flow-tenant-policy-org-uuid-123"]
    }
    service = TenantVaultProvisioningService(vault_client=fake_vault_client)

    result = service.provision_tenant_identity("org-uuid-123")

    assert result.secret_id is None
    assert result.secret_id_accessor is None
    assert result.created_new_secret_id is False
    assert fake_vault_client.secret_id_calls == []


def test_provision_tenant_identity_sanitizes_policy_and_role_names(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle-custom")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "tenant policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "tenant/role")

    fake_vault_client = FakeTenantProvisioningVaultClient()
    service = TenantVaultProvisioningService(vault_client=fake_vault_client)

    result = service.provision_tenant_identity("tenant / blue")

    assert result.policy_name == "tenant-policy-tenant-blue"
    assert result.role_name == "tenant-role-tenant-blue"
    assert fake_vault_client.approle_calls[0]["mount_point"] == "approle-custom"


def test_provision_tenant_identity_rejects_empty_tenant_id(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")

    fake_vault_client = FakeTenantProvisioningVaultClient()
    service = TenantVaultProvisioningService(vault_client=fake_vault_client)

    with pytest.raises(ValueError, match="tenant_id must not be empty."):
        service.provision_tenant_identity("   ")

    assert fake_vault_client.policy_calls == []
