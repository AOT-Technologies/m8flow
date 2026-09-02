"""Where connector profile secrets are stored.

Every sensitive profile value goes through this seam rather than through
connector code directly. Today it delegates to the platform's existing
Fernet-backed secret service; swapping in another store (Vault KV v2, say)
means adding an implementation here and changing nothing else. That is the
whole preparation for Vault -- no second backend ships now.

Tenant scoping is not re-implemented here: models/tenant_schema.py adds
m8f_tenant_id to SecretModel and drops upstream's global unique on `key`, and
tenant_scoping_patch.py filters and stamps every query, so a lookup made in
tenant A's request context cannot see tenant B's secrets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecretProviderCapabilities:
    """Capabilities required to choose a connector secret provider safely.

    Connector profiles will eventually keep every sensitive field in one
    provider document. The control plane must be able to write that document
    without reading it, while the private runtime must be able to read it and
    merge it with database-held non-sensitive settings. Providers declare
    these facts explicitly so a legacy key/value store cannot be selected by
    accident for that target architecture.
    """

    supports_secret_documents: bool = False
    supports_document_compare_and_set: bool = False
    supports_write_only_control_plane: bool = False
    supports_runtime_read: bool = False

    def missing_from(self, required: "SecretProviderCapabilities") -> tuple[str, ...]:
        """Return required capabilities this provider does not implement."""
        return tuple(
            name
            for name in (
                "supports_secret_documents",
                "supports_document_compare_and_set",
                "supports_write_only_control_plane",
                "supports_runtime_read",
            )
            if getattr(required, name) and not getattr(self, name)
        )


CONNECTOR_PROFILE_PROVIDER_CAPABILITIES = SecretProviderCapabilities(
    supports_secret_documents=True,
    supports_document_compare_and_set=True,
    supports_write_only_control_plane=True,
    supports_runtime_read=True,
)


class SecretProviderCapabilityError(RuntimeError):
    """Raised when a provider cannot support the requested connector workflow."""


class SecretBackend(Protocol):
    """Legacy key/value operations plus a declared provider capability set."""

    capabilities: SecretProviderCapabilities

    def create(self, key: str, value: str, user_id: int | None) -> None: ...

    def get(self, key: str) -> str | None: ...

    def upsert(self, key: str, value: str, user_id: int | None) -> None: ...

    def delete(self, key: str) -> None: ...


class SecretDocumentBackend(Protocol):
    """Provider contract for one connector profile secret document.

    The control plane writes without reading, while the private runtime reads
    the complete document. ``expected_version`` is the provider CAS value used
    to prevent lost updates during concurrent profile edits.
    """

    capabilities: SecretProviderCapabilities

    def write_document(
        self,
        key: str,
        values: dict[str, str],
        user_id: int | None,
        expected_version: str | None = None,
    ) -> str | None: ...

    def read_document(self, key: str) -> dict[str, Any] | None: ...

    def delete_document(self, key: str) -> None: ...


class PlatformSecretBackend:
    """Legacy SecretBackend over the platform's existing secret service.

    This provider is intentionally not declared capable of the target
    connector architecture: it stores individual values and lets this process
    read them. It remains available only while legacy profiles are migrated.
    """

    capabilities = SecretProviderCapabilities(
        supports_secret_documents=False,
        supports_document_compare_and_set=False,
        supports_write_only_control_plane=False,
        supports_runtime_read=True,
    )

    def create(self, key: str, value: str, user_id: int | None) -> None:
        from spiffworkflow_backend.services.secret_service import SecretService

        SecretService.add_secret(key=key, value=value, user_id=user_id)

    # ponytail: get/delete read and remove the SecretModel row directly, while
    # create/upsert go through SecretService (which secret_service_patch swaps
    # out). Equivalent today because secrets live in the database. Route these
    # two through SecretService.get_secret/delete_secret before enabling the
    # Vault backend, or profiles will write to Vault and read back nothing.
    def get(self, key: str) -> str | None:
        from spiffworkflow_backend.models.db import db
        from spiffworkflow_backend.models.secret_model import SecretModel
        from spiffworkflow_backend.services.secret_service import SecretService

        secret = db.session.query(SecretModel).filter(SecretModel.key == key).first()
        if secret is None:
            return None
        return SecretService._decrypt(secret.value)

    def upsert(self, key: str, value: str, user_id: int | None) -> None:
        from spiffworkflow_backend.services.secret_service import SecretService

        SecretService.update_secret(
            key=key, value=value, user_id=user_id, create_if_not_exists=True
        )

    def delete(self, key: str) -> None:
        """Remove a secret. An absent key is not an error.

        Deletion is best effort by design: the configuration row is the record
        of truth, and a secret left behind by a failed delete is unreachable
        (nothing references it) rather than a leak of live credentials.
        """
        from spiffworkflow_backend.models.db import db
        from spiffworkflow_backend.models.secret_model import SecretModel

        secret = db.session.query(SecretModel).filter(SecretModel.key == key).first()
        if secret is None:
            return
        db.session.delete(secret)


class VaultConnectorSecretDocumentBackend:
    """Vault KV document provider for the connector storage cutover.

    Tenant identity is included in the logical key and verified against the
    active tenant before the scoped client is used. Vault KV v2
    versions provide the compare-and-set primitive required by profile
    updates.
    """

    capabilities = SecretProviderCapabilities(
        supports_secret_documents=True,
        supports_document_compare_and_set=True,
        supports_write_only_control_plane=True,
        supports_runtime_read=True,
    )

    def __init__(self, tenant_client_provider=None) -> None:
        from m8flow_backend.services.tenant_scoped_vault_client_provider import (
            get_tenant_scoped_vault_client_provider,
        )

        self._tenant_client_provider = (
            tenant_client_provider or get_tenant_scoped_vault_client_provider()
        )

    def write_document(
        self,
        key: str,
        values: dict[str, str],
        user_id: int | None,
        expected_version: str | None = None,
    ) -> str | None:
        del user_id
        tenant_client = self._tenant_client(key)
        response = tenant_client.vault_client.store_secret_document(
            key, values, expected_version=expected_version
        )
        metadata = ((response.get("data") or {}).get("metadata") or {})
        version = metadata.get("version")
        return str(version) if version is not None else None

    def read_document(self, key: str) -> dict[str, Any] | None:
        tenant_client = self._tenant_client(key)
        return tenant_client.vault_client.retrieve_secret_document(key)

    def delete_document(self, key: str) -> None:
        tenant_client = self._tenant_client(key)
        tenant_client.vault_client.delete_secret(key)

    def _tenant_client(self, key: str):
        from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none

        tenant_id = current_tenant_id_or_none()
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SecretProviderCapabilityError("Missing tenant context for connector secret document.")
        from m8flow_backend.services.vault_path_utils import vault_safe_tenant_path_component

        expected_prefix = (
            f"tenants/{vault_safe_tenant_path_component(tenant_id.strip())}/"
            "secrets/connector-configuration/"
        )
        identifier = key[len(expected_prefix) :] if key.startswith(expected_prefix) else ""
        if not identifier.isdigit() or int(identifier) <= 0:
            raise SecretProviderCapabilityError("Connector secret document is outside the active tenant scope.")
        return self._tenant_client_provider.for_tenant(tenant_id.strip())


_legacy_backend: SecretBackend = PlatformSecretBackend()
_backend: SecretBackend = _legacy_backend


def secret_backend() -> SecretBackend:
    # Vault connector profiles use the document provider after startup selects
    # Vault. Tests and legacy deployments can replace this explicitly.
    if _backend is _legacy_backend:
        try:
            from flask import current_app, has_app_context
            from m8flow_backend.config import vault_enabled

            if has_app_context() and (
                current_app.config.get("M8FLOW_SECRET_BACKEND_KIND") == "vault"
                or vault_enabled()
            ):
                return VaultConnectorSecretDocumentBackend()
        except RuntimeError:
            pass
    return _backend


def set_secret_backend(backend: SecretBackend) -> None:
    """Swap the backend. For tests, and for a future Vault rollout."""
    global _backend
    _backend = backend


def require_provider_capabilities(
    backend: SecretBackend,
    required: SecretProviderCapabilities = CONNECTOR_PROFILE_PROVIDER_CAPABILITIES,
) -> None:
    """Fail before a target connector workflow uses an unsuitable provider.

    The legacy CRUD profile implementation deliberately does not call this:
    it has not yet been migrated to provider documents. The cutover service
    will call it before issuing any document write or runtime read.
    """
    capabilities = getattr(backend, "capabilities", SecretProviderCapabilities())
    missing = capabilities.missing_from(required)
    if missing:
        raise SecretProviderCapabilityError(
            "Connector secret provider does not support required capabilities: "
            + ", ".join(missing)
        )


def document_backend() -> SecretDocumentBackend:
    """Return the configured provider only when it implements documents."""
    backend = secret_backend()
    require_provider_capabilities(backend)
    if not all(
        callable(getattr(backend, method, None))
        for method in ("write_document", "read_document", "delete_document")
    ):
        raise SecretProviderCapabilityError(
            "Connector secret provider declares document support but does not "
            "implement the document operations."
        )
    return backend  # type: ignore[return-value]
