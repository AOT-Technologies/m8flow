"""Tests for the manual configuration-variable Vault path migration."""

from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from m8flow_backend.services import named_value_vault_migration as migration


class _VaultClient:
    def __init__(self, documents, fail_writes: bool = False):
        self.documents = documents
        self.fail_writes = fail_writes
        self.deletes = []

    def retrieve_secret_document(self, key):
        return self.documents.get(key)

    def store_secret_document(self, key, document):
        if self.fail_writes:
            raise RuntimeError("Vault write failed")
        self.documents[key] = document

    def delete_secret(self, key):
        self.deletes.append(key)
        self.documents.pop(key, None)


class _Provider:
    def __init__(self, client):
        self.client = client

    def for_tenant(self, _tenant_id):
        return SimpleNamespace(vault_client=self.client)


def _setup(monkeypatch, documents, *, fail_writes: bool = False):
    tenant = SimpleNamespace(id="tenant-a")
    row = SimpleNamespace(
        id="immutable-id",
        m8f_tenant_id="tenant-a",
        name="MUTABLE_NAME",
        is_sensitive=True,
    )
    monkeypatch.setattr(migration, "_tenant_rows", lambda: [tenant])
    monkeypatch.setattr(migration, "_sensitive_rows", lambda _tenant_id: [row])
    return _VaultClient(documents, fail_writes=fail_writes), row


def test_migrates_prior_uuid_path_to_namespaced_minimal_document(monkeypatch) -> None:
    old_key = "tenants/tenant-a/secrets/immutable-id"
    client, row = _setup(monkeypatch, {old_key: {"value": "secret", "name": "ignored"}})

    with Flask(__name__).app_context():
        result = migration.migrate_legacy_named_value_documents(
            tenant_client_provider=_Provider(client)
        )

    target_key = migration.vault_provider_key(row.m8f_tenant_id, row.id)
    assert client.documents[target_key] == {"value": "secret"}
    assert old_key not in client.documents
    assert result.migrated == 1
    assert result.failures == 0


def test_failed_migration_retains_prior_uuid_value(monkeypatch) -> None:
    old_key = "tenants/tenant-a/secrets/immutable-id"
    client, _row = _setup(monkeypatch, {old_key: {"value": "secret"}}, fail_writes=True)

    with Flask(__name__).app_context():
        result = migration.migrate_legacy_named_value_documents(
            tenant_client_provider=_Provider(client)
        )

    assert client.documents[old_key] == {"value": "secret"}
    assert client.deletes == []
    assert result.failures == 1
