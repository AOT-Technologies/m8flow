from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from m8flow_backend.config import vault_approle_mount_point
from m8flow_backend.services.tenant_vault_provisioning_service import TenantVaultProvisioningService
from m8flow_backend.services.vault_client import (
    VaultAppRoleSecretId,
    VaultClient,
    VaultClientError,
    VaultSettings,
    get_vault_client,
)


class TenantScopedVaultClientError(RuntimeError):
    """Raised when a tenant-scoped Vault client cannot be created."""


@dataclass(frozen=True)
class TenantScopedVaultClient:
    """Tenant-isolated Vault client derived from the tenant AppRole."""

    tenant_id: str
    role_name: str
    role_id: str
    secret_id_accessor: str | None
    vault_client: VaultClient


VaultClientBuilder = Callable[[VaultSettings], VaultClient]


class TenantScopedVaultClientProvider:
    """Resolve tenant-specific Vault clients from pre-provisioned tenant AppRoles."""

    def __init__(
        self,
        broker_vault_client: VaultClient | None = None,
        vault_client_builder: VaultClientBuilder | None = None,
    ) -> None:
        self._broker_vault_client = broker_vault_client or get_vault_client()
        self._vault_client_builder = vault_client_builder or (lambda settings: VaultClient(settings=settings))

    def for_tenant(self, tenant_id: str) -> TenantScopedVaultClient:
        normalized_tenant_id = self._require_non_empty(tenant_id, "tenant_id")
        role_name = TenantVaultProvisioningService.tenant_role_name(normalized_tenant_id)
        approle_mount = self._require_non_empty(vault_approle_mount_point(), "vault_approle_mount_point")

        try:
            role = self._broker_vault_client.read_approle(
                role_name,
                mount_point=approle_mount,
            )
            if role is None:
                raise TenantScopedVaultClientError(
                    f"Vault AppRole '{role_name}' does not exist for tenant '{normalized_tenant_id}'."
                )

            role_id = self._broker_vault_client.read_approle_role_id(
                role_name,
                mount_point=approle_mount,
            )
            secret_id = self._broker_vault_client.generate_approle_secret_id(
                role_name,
                mount_point=approle_mount,
            )
        except TenantScopedVaultClientError:
            raise
        except VaultClientError as exc:
            raise TenantScopedVaultClientError(
                f"Could not resolve a tenant-scoped Vault client for tenant '{normalized_tenant_id}': {exc}"
            ) from exc

        tenant_settings = self._tenant_settings(secret_id=secret_id, role_id=role_id)
        tenant_vault_client = self._vault_client_builder(tenant_settings)

        return TenantScopedVaultClient(
            tenant_id=normalized_tenant_id,
            role_name=role_name,
            role_id=role_id,
            secret_id_accessor=secret_id.secret_id_accessor,
            vault_client=tenant_vault_client,
        )

    def _tenant_settings(self, *, secret_id: VaultAppRoleSecretId, role_id: str) -> VaultSettings:
        return self._broker_vault_client.settings.with_approle_credentials(
            role_id=role_id,
            secret_id=secret_id.secret_id,
        )

    @staticmethod
    def _require_non_empty(value: str, field_name: str) -> str:
        normalized_value = (value or "").strip()
        if not normalized_value:
            raise ValueError(f"{field_name} must not be empty.")
        return normalized_value


def get_tenant_scoped_vault_client_provider() -> TenantScopedVaultClientProvider:
    return TenantScopedVaultClientProvider()
