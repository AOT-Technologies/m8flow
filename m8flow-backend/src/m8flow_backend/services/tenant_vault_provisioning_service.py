from __future__ import annotations

from dataclasses import dataclass
import re

from m8flow_backend.config import vault_enabled
from m8flow_backend.config import (
    vault_approle_mount_point,
    vault_mount_point,
    vault_secret_path_prefix,
    vault_tenant_secret_id_num_uses,
    vault_tenant_secret_id_ttl,
    vault_tenant_token_max_ttl,
    vault_tenant_token_ttl,
    vault_tenant_policy_prefix,
    vault_tenant_role_prefix,
)
from m8flow_backend.services.vault_client import (
    VaultAppRoleSecretId,
    VaultClient,
    get_vault_client,
)
from m8flow_backend.services.vault_path_utils import vault_safe_tenant_path_component

_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class TenantVaultIdentity:
    """Vault identity artifacts provisioned for a single tenant."""

    tenant_id: str
    policy_name: str
    role_name: str
    role_id: str
    secret_id: str | None = None
    secret_id_accessor: str | None = None
    created_new_secret_id: bool = False


class TenantVaultProvisioningError(RuntimeError):
    """Raised when tenant-scoped Vault provisioning cannot be completed."""


class TenantVaultProvisioningService:
    """Provision Vault-side tenant isolation artifacts."""

    def __init__(
        self,
        vault_client: VaultClient | None = None,
    ) -> None:
        self._vault_client = vault_client or get_vault_client()

    def provision_tenant_identity(self, tenant_id: str) -> TenantVaultIdentity:
        normalized_tenant_id = self._require_non_empty(tenant_id, "tenant_id")
        policy_name = self.tenant_policy_name(normalized_tenant_id)
        role_name = self.tenant_role_name(normalized_tenant_id)
        approle_mount = self._require_non_empty(vault_approle_mount_point(), "vault_approle_mount_point")
        try:
            existing_role = self._vault_client.read_approle(
                role_name,
                mount_point=approle_mount,
            )
            self._vault_client.create_or_update_policy(
                policy_name,
                self._tenant_policy(normalized_tenant_id),
            )
            self._vault_client.create_or_update_approle(
                role_name,
                mount_point=approle_mount,
                token_policies=[policy_name],
                secret_id_num_uses=vault_tenant_secret_id_num_uses(),
                secret_id_ttl=vault_tenant_secret_id_ttl(),
                token_ttl=vault_tenant_token_ttl(),
                token_max_ttl=vault_tenant_token_max_ttl(),
            )
            role_id = self._vault_client.read_approle_role_id(
                role_name,
                mount_point=approle_mount,
            )
            secret_id: VaultAppRoleSecretId | None = None
            if existing_role is None:
                secret_id = self._vault_client.generate_approle_secret_id(
                    role_name,
                    mount_point=approle_mount,
                )
        except Exception as exc:
            raise TenantVaultProvisioningError(
                f"Could not provision Vault identity for tenant '{normalized_tenant_id}': {exc}"
            ) from exc

        return TenantVaultIdentity(
            tenant_id=normalized_tenant_id,
            policy_name=policy_name,
            role_name=role_name,
            role_id=role_id,
            secret_id=secret_id.secret_id if secret_id is not None else None,
            secret_id_accessor=secret_id.secret_id_accessor if secret_id is not None else None,
            created_new_secret_id=secret_id is not None,
        )

    @classmethod
    def tenant_policy_name(cls, tenant_id: str) -> str:
        normalized_tenant_id = cls._require_non_empty(tenant_id, "tenant_id")
        return cls._identity_name(vault_tenant_policy_prefix(), normalized_tenant_id)

    @classmethod
    def tenant_role_name(cls, tenant_id: str) -> str:
        normalized_tenant_id = cls._require_non_empty(tenant_id, "tenant_id")
        return cls._identity_name(vault_tenant_role_prefix(), normalized_tenant_id)

    @classmethod
    def _tenant_policy(cls, tenant_id: str) -> str:
        mount_point = cls._require_non_empty(vault_mount_point(), "vault_mount_point")
        policy_paths = []
        for root in (cls._tenant_secret_root(tenant_id), cls._tenant_connector_root(tenant_id)):
            policy_paths.append(
                f'path "{mount_point}/data/{root}/*" {{\n'
                '  capabilities = ["create", "read", "update", "delete"]\n'
                "}\n\n"
                f'path "{mount_point}/metadata/{root}" {{\n'
                '  capabilities = ["list", "read"]\n'
                "}\n\n"
                f'path "{mount_point}/metadata/{root}/*" {{\n'
                '  capabilities = ["list", "read", "delete"]\n'
                "}\n"
            )
        return "\n".join(policy_paths)

    @classmethod
    def _tenant_secret_root(cls, tenant_id: str) -> str:
        prefix = cls._require_non_empty(vault_secret_path_prefix(), "vault_secret_path_prefix")
        return cls._join_vault_path(
            prefix,
            "tenants",
            vault_safe_tenant_path_component(tenant_id),
            "secrets",
        )

    @classmethod
    def _tenant_connector_root(cls, tenant_id: str) -> str:
        prefix = cls._require_non_empty(vault_secret_path_prefix(), "vault_secret_path_prefix")
        return cls._join_vault_path(
            prefix,
            "tenants",
            vault_safe_tenant_path_component(tenant_id),
            "secrets",
            "connector-configuration",
        )

    @classmethod
    def _identity_name(cls, prefix: str, tenant_id: str) -> str:
        normalized_prefix = cls._sanitize_name_component(prefix, "prefix")
        normalized_tenant = cls._sanitize_name_component(tenant_id, "tenant_id")
        return f"{normalized_prefix}-{normalized_tenant}"

    @staticmethod
    def _join_vault_path(*parts: str) -> str:
        return "/".join(part.strip().strip("/") for part in parts if part and part.strip().strip("/"))

    @staticmethod
    def _sanitize_name_component(value: str, field_name: str) -> str:
        normalized_value = TenantVaultProvisioningService._require_non_empty(value, field_name)
        sanitized_value = _SAFE_NAME_PATTERN.sub("-", normalized_value).strip("-.")
        if not sanitized_value:
            raise ValueError(f"{field_name} must contain at least one Vault-safe character.")
        return sanitized_value

    @staticmethod
    def _require_non_empty(value: str, field_name: str) -> str:
        normalized_value = (value or "").strip()
        if not normalized_value:
            raise ValueError(f"{field_name} must not be empty.")
        return normalized_value


def get_tenant_vault_provisioning_service() -> TenantVaultProvisioningService:
    return TenantVaultProvisioningService()


def provision_tenant_vault_identity_if_enabled(tenant_id: str) -> TenantVaultIdentity | None:
    if not vault_enabled():
        return None
    return get_tenant_vault_provisioning_service().provision_tenant_identity(tenant_id)
