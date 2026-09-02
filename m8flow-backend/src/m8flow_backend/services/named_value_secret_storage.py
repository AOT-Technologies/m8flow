"""Storage seam for the payload of sensitive manual configuration variables."""

from __future__ import annotations

from typing import Protocol

from flask import current_app, has_app_context

from m8flow_backend.models.named_value import NamedValueModel
from m8flow_backend.services.secret_backend import get_secret_backend
from m8flow_backend.services.tenant_scoped_vault_client_provider import (
    TenantScopedVaultClientProvider,
    get_tenant_scoped_vault_client_provider,
)
from m8flow_backend.services.vault_path_utils import vault_safe_tenant_path_component
from spiffworkflow_backend.exceptions.api_error import ApiError


class NamedValueSecretStorage(Protocol):
    """Persist only a manual sensitive variable's plaintext payload."""

    def write(self, row: NamedValueModel, value: str) -> None: ...

    def read(self, row: NamedValueModel) -> str | None: ...

    def delete(self, row: NamedValueModel) -> None: ...


def vault_provider_key(tenant_id: str, named_value_id: str) -> str:
    """Return the immutable tenant-scoped Vault key for a manual variable."""
    normalized_id = str(named_value_id or "").strip()
    if not normalized_id:
        raise ValueError("named_value_id must not be empty.")
    return (
        f"tenants/{vault_safe_tenant_path_component(tenant_id)}"
        f"/secrets/configuration-variable/{normalized_id}"
    )


def legacy_provider_key(named_value_id: str) -> str:
    """Avoid coupling legacy secret-table records to a mutable variable name."""
    normalized_id = str(named_value_id or "").strip()
    if not normalized_id:
        raise ValueError("named_value_id must not be empty.")
    return f"named-value:{normalized_id}"


class VaultNamedValueSecretStorage:
    """Vault KV storage for the value-only manual-variable document."""

    def __init__(self, tenant_client_provider: TenantScopedVaultClientProvider | None = None) -> None:
        self._tenant_client_provider = tenant_client_provider or get_tenant_scoped_vault_client_provider()

    def write(self, row: NamedValueModel, value: str) -> None:
        self._client(row).store_secret_document(self._key(row), {"value": value})

    def read(self, row: NamedValueModel) -> str | None:
        document = self._client(row).retrieve_secret_document(self._key(row))
        return self._document_value(document)

    def delete(self, row: NamedValueModel) -> None:
        self._client(row).delete_secret(self._key(row))

    @staticmethod
    def _document_value(document: dict[str, object] | None) -> str | None:
        if not isinstance(document, dict):
            return None
        value = document.get("value")
        return value if isinstance(value, str) else None

    def _client(self, row: NamedValueModel):
        return self._tenant_client_provider.for_tenant(row.m8f_tenant_id).vault_client

    @staticmethod
    def _key(row: NamedValueModel) -> str:
        return vault_provider_key(row.m8f_tenant_id, row.id)


class LegacyNamedValueSecretStorage:
    """Existing encrypted secret-table fallback when Vault is disabled."""

    def write(self, row: NamedValueModel, value: str) -> None:
        backend = get_secret_backend()
        key = legacy_provider_key(row.id)
        try:
            backend.update_secret(key, value, user_id=row.user_id, create_if_not_exists=True)
        except ApiError:
            backend.add_secret(key, value, row.user_id or 0)

    def read(self, row: NamedValueModel) -> str | None:
        backend = get_secret_backend()
        try:
            return backend.get_secret_value(legacy_provider_key(row.id))
        except ApiError:
            # Variables created before this refactor used their mutable name.
            try:
                return backend.get_secret_value(row.name)
            except ApiError:
                return None

    def delete(self, row: NamedValueModel) -> None:
        backend = get_secret_backend()
        try:
            backend.delete_secret(legacy_provider_key(row.id), row.user_id or 0)
        except ApiError:
            # A legacy record may still be keyed by the old variable name.
            try:
                backend.delete_secret(row.name, row.user_id or 0)
            except ApiError:
                pass


def get_named_value_secret_storage() -> NamedValueSecretStorage:
    """Choose Vault only after application startup selected Vault storage."""
    if has_app_context() and current_app.config.get("M8FLOW_SECRET_BACKEND_KIND") == "vault":
        return VaultNamedValueSecretStorage()
    return LegacyNamedValueSecretStorage()
