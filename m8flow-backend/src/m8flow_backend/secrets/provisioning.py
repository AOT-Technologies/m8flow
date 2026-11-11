"""Per-tenant Vault AppRole + policy, provisioned when a tenant is created."""

from __future__ import annotations

import hashlib
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


class TenantVaultCleanupError(RuntimeError):
    """Tenant-scoped Vault data could not be removed after tenant deletion."""


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


def _tenant_component(tenant_id: str) -> str:
    normalized = _require(tenant_id, "tenant_id")
    sanitized = _safe_component(normalized, "tenant_id")
    if sanitized == normalized:
        return sanitized
    # Keep Vault-safe names readable while ensuring lossy sanitization cannot
    # alias two distinct tenant IDs to the same AppRole or policy.
    suffix = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{sanitized}-{suffix}"


def tenant_policy_name(tenant_id: str) -> str:
    return f"{_safe_component(vault_tenant_policy_prefix(), 'prefix')}-{_tenant_component(tenant_id)}"


def tenant_role_name(tenant_id: str) -> str:
    return f"{_safe_component(vault_tenant_role_prefix(), 'prefix')}-{_tenant_component(tenant_id)}"


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


def _normalized_policy(policy: str | None) -> str | None:
    if policy is None:
        return None
    return "\n".join(line.strip() for line in policy.splitlines() if line.strip())


def reconcile_tenant_identity(
    tenant_id: str, *, control: Any | None = None
) -> TenantVaultIdentity:
    """Ensure a tenant role and its policy match the current isolation contract.

    Tenant rows may predate Vault or may retain roles after an interrupted or
    manually edited provisioning operation. Check both the policy document and
    the role's policy binding before allowing the caller to mint a tenant token.
    Repair is idempotent and does not rotate SecretIDs for an existing role.
    """
    normalized = _require(tenant_id, "tenant_id")
    policy_name = tenant_policy_name(normalized)
    role_name = tenant_role_name(normalized)
    mount = _require(vault_approle_mount_point(), "vault_approle_mount_point")
    admin = control if control is not None else HttpVault.from_env()
    try:
        role = admin.read_approle(role_name, mount=mount)
        current_policy = admin.read_policy(policy_name)
        role_data = role.get("data") if isinstance(role, dict) else None
        if not isinstance(role_data, dict):
            role_data = role if isinstance(role, dict) else {}
        bound_policies = role_data.get("token_policies")
        if not isinstance(bound_policies, list):
            bound_policies = role_data.get("policies")
        if not isinstance(bound_policies, list):
            bound_policies = []

        expected_policy = _tenant_policy(normalized)
        policy_is_current = _normalized_policy(current_policy) == _normalized_policy(
            expected_policy
        )
        role_is_current = (
            set(str(policy) for policy in bound_policies) == {policy_name}
            and role_data.get("token_no_default_policy") is True
        )
        if not policy_is_current or not role_is_current:
            return provision_tenant_identity(normalized, control=admin)

        role_id = admin.read_approle_role_id(role_name, mount=mount)
    except (TenantVaultProvisioningError, ValueError):
        raise
    except Exception as exc:
        raise TenantVaultProvisioningError(
            f"Could not reconcile Vault identity for tenant '{normalized}'."
        ) from exc

    return TenantVaultIdentity(
        tenant_id=normalized,
        policy_name=policy_name,
        role_name=role_name,
        role_id=role_id,
    )


def provision_vault_identity_if_enabled(tenant_id: str) -> TenantVaultIdentity | None:
    if resolved_secret_backend_kind() != "vault":
        return None
    try:
        return provision_tenant_identity(tenant_id)
    except VaultTransportError as exc:
        raise TenantVaultProvisioningError("Could not provision Vault identity.") from exc


def delete_tenant_vault_data(tenant_id: str, *, control: Any | None = None) -> None:
    """Delete a tenant's KV v2 subtree using that tenant's restricted token.

    Call only after the tenant database deletion commits. This deliberately
    does not delete the shared broker's AppRole or policy; identity retirement
    requires an operator-controlled Vault credential, not wider runtime ACLs.
    """
    if resolved_secret_backend_kind() != "vault":
        return
    normalized = _require(tenant_id, "tenant_id")
    role_name = tenant_role_name(normalized)
    broker = control if control is not None else HttpVault.from_env()
    try:
        tenant_store = broker.store_for_tenant(normalized, role_name=role_name)
        tenant_store.delete_tree(secret_root(normalized))
    except Exception as exc:
        raise TenantVaultCleanupError(
            f"Could not remove Vault secret data for tenant '{normalized}'."
        ) from exc
