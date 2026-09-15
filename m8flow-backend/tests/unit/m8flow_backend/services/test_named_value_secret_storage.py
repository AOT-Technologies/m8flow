"""Tests for value-only Vault documents of manual configuration variables."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from m8flow_backend.services.named_value_secret_storage import (
    VaultNamedValueSecretStorage,
    vault_provider_key,
)


class _VaultClient:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, str]] = {}
        self.writes: list[tuple[str, dict[str, str]]] = []
        self.reads: list[str] = []
        self.deletes: list[str] = []

    def store_secret_document(self, key: str, document: dict[str, str]) -> None:
        self.writes.append((key, document))
        self.documents[key] = document

    def retrieve_secret_document(self, key: str):
        self.reads.append(key)
        return self.documents.get(key)

    def delete_secret(self, key: str) -> bool:
        self.deletes.append(key)
        return self.documents.pop(key, None) is not None


class _Provider:
    def __init__(self) -> None:
        self.client = _VaultClient()
        self.tenant_ids: list[str] = []

    def for_tenant(self, tenant_id: str):
        self.tenant_ids.append(tenant_id)
        return SimpleNamespace(vault_client=self.client)


def _row(tenant_id: str = "tenant/one", value_id: str = "immutable-id"):
    return SimpleNamespace(m8f_tenant_id=tenant_id, id=value_id, name="MUTABLE_NAME")


def test_manual_sensitive_vault_document_is_value_only_and_id_keyed() -> None:
    provider = _Provider()
    storage = VaultNamedValueSecretStorage(provider)
    row = _row()

    storage.write(row, "sensitive-value")

    key = "tenants/tenant%2Fone/secrets/configuration-variable/immutable-id"
    assert provider.client.writes == [(key, {"value": "sensitive-value"})]
    assert provider.tenant_ids == ["tenant/one"]
    assert storage.read(row) == "sensitive-value"
    assert provider.client.reads == [key]
    storage.delete(row)
    assert provider.client.deletes == [key]


def test_manual_sensitive_vault_document_isolated_by_tenant_and_ignores_mutable_name() -> None:
    assert vault_provider_key("tenant-a", "fixed-id") == (
        "tenants/tenant-a/secrets/configuration-variable/fixed-id"
    )
    assert vault_provider_key("tenant-b", "fixed-id") == (
        "tenants/tenant-b/secrets/configuration-variable/fixed-id"
    )


def test_renaming_a_manual_variable_does_not_change_its_vault_key() -> None:
    row = _row()
    original_key = vault_provider_key(row.m8f_tenant_id, row.id)

    row.name = "RENAMED_VARIABLE"

    assert vault_provider_key(row.m8f_tenant_id, row.id) == original_key


def test_manual_sensitive_storage_never_reads_metadata_fields() -> None:
    provider = _Provider()
    storage = VaultNamedValueSecretStorage(provider)
    row = _row()
    provider.client.documents[
        "tenants/tenant%2Fone/secrets/configuration-variable/immutable-id"
    ] = {
        "value": "secret",
        "name": "old-metadata",
    }

    assert storage.read(row) == "secret"


def test_manual_sensitive_provider_key_requires_id() -> None:
    with pytest.raises(ValueError, match="named_value_id"):
        vault_provider_key("tenant-a", "")
