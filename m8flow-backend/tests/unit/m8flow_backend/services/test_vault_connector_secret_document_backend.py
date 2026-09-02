"""Tests for the tenant-bound Vault connector document adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from m8flow_backend.services.connector_secret_backend import (
    SecretProviderCapabilityError,
    VaultConnectorSecretDocumentBackend,
)


class _VaultClient:
    def __init__(self):
        self.writes = []
        self.reads = []
        self.deletes = []

    def store_secret_document(self, key, values, expected_version=None):
        self.writes.append((key, values))
        return {"data": {"metadata": {"version": 4}}}

    def retrieve_secret_document(self, key):
        self.reads.append(key)
        return {"token": "value"}

    def delete_secret(self, key):
        self.deletes.append(key)


class _Provider:
    def __init__(self):
        self.client = _VaultClient()

    def for_tenant(self, tenant_id):
        return SimpleNamespace(tenant_id=tenant_id, vault_client=self.client)


def test_vault_document_adapter_uses_active_tenant_scope():
    provider = _Provider()
    backend = VaultConnectorSecretDocumentBackend(provider)

    with patch(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_id_or_none",
        return_value="tenant/one",
    ):
        key = "tenants/tenant%2Fone/secrets/connector-configuration/17"
        backend.write_document(key, {"TOKEN": "value"}, 7)
        assert backend.read_document(key) == {"token": "value"}
        backend.delete_document(key)

    assert provider.client.writes == [(key, {"TOKEN": "value"})]
    assert provider.client.reads == [key]
    assert provider.client.deletes == [key]


def test_vault_document_adapter_rejects_cross_tenant_key():
    backend = VaultConnectorSecretDocumentBackend(_Provider())

    with patch(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_id_or_none",
        return_value="tenant/one",
    ), pytest.raises(SecretProviderCapabilityError, match="outside"):
        backend.read_document("tenants/tenant-two/secrets/connector-configuration/17")


def test_vault_document_adapter_passes_cas_to_vault():
    backend = VaultConnectorSecretDocumentBackend(_Provider())

    with patch(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_id_or_none",
        return_value="tenant-one",
    ):
        assert backend.write_document(
            "tenants/tenant-one/secrets/connector-configuration/17", {"token": "value"}, 7, "3"
        ) == "4"
