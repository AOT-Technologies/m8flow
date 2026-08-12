from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from m8flow_backend.config import vault_enabled
from m8flow_backend.config import (
    vault_approle_mount_point,
    vault_mount_point,
    vault_secret_path_prefix,
    vault_tenant_policy_prefix,
    vault_tenant_role_prefix,
)
from m8flow_backend.services.vault_client import (
    VaultAppRoleSecretId,
    VaultClient,
    VaultSettings,
    get_vault_client,
)

_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_BOOTSTRAP_MARKER_PATH = "bootstrap"
_BOOTSTRAP_MARKER_STATUS_FIELD = "status"
_BOOTSTRAP_MARKER_STATUS_VALUE = "initialized"


VaultClientBuilder = Callable[[VaultSettings], VaultClient]


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
        vault_client_builder: VaultClientBuilder | None = None,
    ) -> None:
        self._vault_client = vault_client or get_vault_client()
        self._vault_client_builder = vault_client_builder or (lambda settings: VaultClient(settings=settings))

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
            bootstrap_secret_id = secret_id or self._vault_client.generate_approle_secret_id(
                role_name,
                mount_point=approle_mount,
            )
            self._ensure_tenant_bootstrap_marker(
                tenant_id=normalized_tenant_id,
                role_id=role_id,
                secret_id=bootstrap_secret_id.secret_id,
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
        secret_root = cls._tenant_secret_root(tenant_id)
        bootstrap_path = cls._tenant_bootstrap_path(tenant_id)
        return (
            f'path "{mount_point}/data/{bootstrap_path}" {{\n'
            '  capabilities = ["create", "read", "update"]\n'
            "}\n\n"
            f'path "{mount_point}/data/{secret_root}/*" {{\n'
            '  capabilities = ["create", "read", "update", "delete"]\n'
            "}\n\n"
            f'path "{mount_point}/metadata/{secret_root}" {{\n'
            '  capabilities = ["list", "read"]\n'
            "}\n\n"
            f'path "{mount_point}/metadata/{secret_root}/*" {{\n'
            '  capabilities = ["list", "read", "delete"]\n'
            "}\n"
        )

    @classmethod
    def _tenant_secret_root(cls, tenant_id: str) -> str:
        prefix = cls._require_non_empty(vault_secret_path_prefix(), "vault_secret_path_prefix")
        return cls._join_vault_path(prefix, "tenants", tenant_id, "secrets")

    @classmethod
    def _tenant_bootstrap_path(cls, tenant_id: str) -> str:
        prefix = cls._require_non_empty(vault_secret_path_prefix(), "vault_secret_path_prefix")
        return cls._join_vault_path(prefix, "tenants", tenant_id, _BOOTSTRAP_MARKER_PATH)

    def _ensure_tenant_bootstrap_marker(self, *, tenant_id: str, role_id: str, secret_id: str) -> None:
        tenant_vault_client = self._tenant_vault_client(role_id=role_id, secret_id=secret_id)
        bootstrap_path = self._tenant_bootstrap_path(tenant_id)
        existing_document = tenant_vault_client.retrieve_secret_document(bootstrap_path)
        if existing_document is not None:
            return
        tenant_vault_client.store_secret_document(
            bootstrap_path,
            {_BOOTSTRAP_MARKER_STATUS_FIELD: _BOOTSTRAP_MARKER_STATUS_VALUE},
        )

    def _tenant_vault_client(self, *, role_id: str, secret_id: str) -> VaultClient:
        tenant_settings = self._vault_client.settings.with_approle_credentials(
            role_id=role_id,
            secret_id=secret_id,
        )
        return self._vault_client_builder(tenant_settings)

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
