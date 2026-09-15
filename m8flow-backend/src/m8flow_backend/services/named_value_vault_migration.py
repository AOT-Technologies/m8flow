"""Value-preserving migration for legacy manual-variable Vault documents."""

from __future__ import annotations

from dataclasses import dataclass

from flask import g

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.models.named_value import NamedValueModel
from m8flow_backend.services.named_value_secret_storage import vault_provider_key
from m8flow_backend.services.tenant_scoped_vault_client_provider import (
    TenantScopedVaultClientProvider,
    get_tenant_scoped_vault_client_provider,
)
from m8flow_backend.services.vault_path_utils import vault_safe_tenant_path_component


@dataclass
class NamedValueVaultMigrationResult:
    migrated: int = 0
    normalized: int = 0
    missing_legacy_value: int = 0
    conflicts: int = 0
    failures: int = 0


def _legacy_uuid_key(row: NamedValueModel) -> str:
    return f"tenants/{vault_safe_tenant_path_component(row.m8f_tenant_id)}/secrets/{row.id}"


def _legacy_name_key(row: NamedValueModel) -> str:
    return f"tenants/{vault_safe_tenant_path_component(row.m8f_tenant_id)}/secrets/{row.name.strip('/')}"


def _legacy_keys(row: NamedValueModel) -> list[str]:
    """Only inspect historical keys derived from the catalog row being migrated."""
    return list(dict.fromkeys((_legacy_uuid_key(row), _legacy_name_key(row))))


def _value(document: dict[str, object] | None) -> str | None:
    if not isinstance(document, dict):
        return None
    value = document.get("value")
    return value if isinstance(value, str) else None


def _write_minimal_payload(client: object, target_key: str, value: str) -> bool:
    """Write and verify before removing a legacy document."""
    client.store_secret_document(target_key, {"value": value})
    return _value(client.retrieve_secret_document(target_key)) == value


def _tenant_rows() -> list[M8flowTenantModel]:
    return M8flowTenantModel.query.order_by(M8flowTenantModel.id).all()


def _sensitive_rows(tenant_id: str) -> list[NamedValueModel]:
    return (
        NamedValueModel.query.filter_by(m8f_tenant_id=tenant_id, is_sensitive=True)
        .order_by(NamedValueModel.id)
        .all()
    )


def migrate_legacy_named_value_documents(
    *,
    tenant_client_provider: TenantScopedVaultClientProvider | None = None,
    dry_run: bool = False,
) -> NamedValueVaultMigrationResult:
    """Move legacy name-keyed documents to minimal ID-keyed documents.

    Existing documents may contain copied catalog metadata. Only their actual
    ``value`` is retained. A conflicting existing ID-keyed value is reported
    and left untouched rather than silently overwriting a credential.
    """
    provider = tenant_client_provider or get_tenant_scoped_vault_client_provider()
    result = NamedValueVaultMigrationResult()

    for tenant in _tenant_rows():
        g.m8flow_tenant_id = tenant.id
        client = provider.for_tenant(tenant.id).vault_client
        for row in _sensitive_rows(tenant.id):
            target_key = vault_provider_key(row.m8f_tenant_id, row.id)
            target_document = client.retrieve_secret_document(target_key)
            target_value = _value(target_document)
            legacy_keys = _legacy_keys(row)

            if target_value is None:
                legacy_key = next(
                    (
                        key
                        for key in legacy_keys
                        if _value(client.retrieve_secret_document(key)) is not None
                    ),
                    None,
                )
                if legacy_key is None:
                    result.missing_legacy_value += 1
                    continue
                legacy_value = _value(client.retrieve_secret_document(legacy_key))
                assert legacy_value is not None
                if not dry_run:
                    try:
                        if not _write_minimal_payload(client, target_key, legacy_value):
                            result.failures += 1
                            continue
                        client.delete_secret(legacy_key)
                    except Exception:
                        # Preserve the old value when copy or cleanup fails.
                        result.failures += 1
                        continue
                result.migrated += 1
                continue

            if target_document != {"value": target_value}:
                if not dry_run:
                    try:
                        if not _write_minimal_payload(client, target_key, target_value):
                            result.failures += 1
                            continue
                    except Exception:
                        result.failures += 1
                        continue
                result.normalized += 1

            for legacy_key in legacy_keys:
                legacy_value = _value(client.retrieve_secret_document(legacy_key))
                if legacy_value is None:
                    continue
                if legacy_value != target_value:
                    result.conflicts += 1
                    continue
                if not dry_run:
                    try:
                        client.delete_secret(legacy_key)
                    except Exception:
                        result.failures += 1

    return result
