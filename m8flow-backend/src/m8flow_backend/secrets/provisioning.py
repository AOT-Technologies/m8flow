"""Per-tenant Vault AppRole + policy, provisioned when a tenant is created."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from m8flow_backend.config import (
    vault_approle_mount_point,
    vault_mount_point,
    vault_tenant_policy_prefix,
    vault_tenant_role_prefix,
    vault_tenant_secret_id_num_uses,
    vault_tenant_secret_id_ttl,
    vault_tenant_token_max_ttl,
    vault_tenant_token_ttl,
)
from m8flow_backend.secrets.http import HttpVault, VaultTransportError
from m8flow_backend.secrets.paths import secret_root
from m8flow_backend.secrets.provider import resolved_secret_backend_kind

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class TenantVaultIdentity:
    tenant_id: str
    policy_name: str
    role_name: str
    role_id: str
    secret_id: str | None = None
    secret_id_accessor: str | None = None
    created_new_secret_id: bool = False


class TenantVaultProvisioningError(RuntimeError):
    """Vault identity for a tenant could not be created. Do not leave the tenant usable."""


def _require(value: str, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _safe_component(value: str, field_name: str) -> str:
    sanitized = _SAFE_NAME.sub("-", _require(value, field_name)).strip("-.")
    if not sanitized:
        raise ValueError(f"{field_name} must contain at least one Vault-safe character.")
    return sanitized


def tenant_policy_name(tenant_id: str) -> str:
    return f"{_safe_component(vault_tenant_policy_prefix(), 'prefix')}-{_safe_component(tenant_id, 'tenant_id')}"


def tenant_role_name(tenant_id: str) -> str:
    return f"{_safe_component(vault_tenant_role_prefix(), 'prefix')}-{_safe_component(tenant_id, 'tenant_id')}"


def _tenant_policy(tenant_id: str) -> str:
    mount = _require(vault_mount_point(), "vault_mount_point")
    root = secret_root(_require(tenant_id, "tenant_id"))
    return (
        f'path "{mount}/data/{root}/*" {{\n'
        '  capabilities = ["create", "read", "update", "delete"]\n'
        "}\n\n"
        f'path "{mount}/metadata/{root}" {{\n'
        '  capabilities = ["list", "read"]\n'
        "}\n\n"
        f'path "{mount}/metadata/{root}/*" {{\n'
        '  capabilities = ["list", "read", "delete"]\n'
        "}\n"
    )


def provision_tenant_identity(tenant_id: str, *, control: Any | None = None) -> TenantVaultIdentity:
    normalized = _require(tenant_id, "tenant_id")
    policy_name = tenant_policy_name(normalized)
    role_name = tenant_role_name(normalized)
    mount = _require(vault_approle_mount_point(), "vault_approle_mount_point")
    admin = control if control is not None else HttpVault.from_env()
    try:
        existing = admin.read_approle(role_name, mount=mount)
        admin.write_policy(policy_name, _tenant_policy(normalized))
        admin.write_approle(
            role_name,
            mount=mount,
            token_policies=[policy_name],
            token_no_default_policy=True,
            secret_id_num_uses=vault_tenant_secret_id_num_uses(),
            secret_id_ttl=vault_tenant_secret_id_ttl(),
            token_ttl=vault_tenant_token_ttl(),
            token_max_ttl=vault_tenant_token_max_ttl(),
        )
        role_id = admin.read_approle_role_id(role_name, mount=mount)
        secret_id = None
        accessor = None
        created_new = False
        if existing is None:
            minted = admin.mint_approle_secret_id(role_name, mount=mount)
            secret_id = minted.secret_id
            accessor = minted.secret_id_accessor
            created_new = True
    except TenantVaultProvisioningError:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise TenantVaultProvisioningError(
            f"Could not provision Vault identity for tenant '{normalized}'."
        ) from exc

    return TenantVaultIdentity(
        tenant_id=normalized,
        policy_name=policy_name,
        role_name=role_name,
        role_id=role_id,
        secret_id=secret_id,
        secret_id_accessor=accessor,
        created_new_secret_id=created_new,
    )


def provision_vault_identity_if_enabled(tenant_id: str) -> TenantVaultIdentity | None:
    if resolved_secret_backend_kind() != "vault":
        return None
    try:
        return provision_tenant_identity(tenant_id)
    except VaultTransportError as exc:
        raise TenantVaultProvisioningError("Could not provision Vault identity.") from exc
