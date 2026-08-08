from __future__ import annotations

from dataclasses import dataclass
import logging
import uuid
from typing import TYPE_CHECKING, Any, Callable

from flask import current_app

from m8flow_backend.config import vault_enabled
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.models.vault_metadata import VaultMetadataModel
from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.services.vault_client import (
    VaultClient,
    VaultClientError,
    VaultConnectionError,
    get_vault_client,
)
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.user import UserModel

if TYPE_CHECKING:
    from spiffworkflow_backend.models.secret_model import SecretModel


logger = logging.getLogger("m8flow.secret_backend")


@dataclass(repr=False)
class ResolvedSecret:
    """Transient secret object compatible with the upstream SecretService contract."""

    id: str | int
    key: str
    user_id: int
    value: str
    updated_at_in_seconds: int | None
    created_at_in_seconds: int | None
    m8f_tenant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "user_id": self.user_id,
            "updated_at_in_seconds": self.updated_at_in_seconds,
            "created_at_in_seconds": self.created_at_in_seconds,
        }

    def __repr__(self) -> str:
        return (
            f"<ResolvedSecret(id={self.id}, key={self.key}, user_id={self.user_id}, "
            f"tenant_id={self.m8f_tenant_id})>"
        )


def _encrypt_secret_value(value: str) -> str:
    from spiffworkflow_backend.services.secret_service import SecretService

    return SecretService._encrypt(value)


def _secret_not_found(key: str) -> ApiError:
    return ApiError(
        error_code="missing_secret_error",
        message=f"Unable to locate a secret with the name: {key}. ",
        status_code=404,
    )


def _vault_secret_missing_value(key: str, tenant_id: str, metadata_id: str, path: str) -> ApiError:
    logger.warning(
        "vault_secret_value_missing tenant_id=%s metadata_id=%s key=%s path=%s",
        tenant_id,
        metadata_id,
        key,
        path,
    )
    return ApiError(
        error_code="vault_secret_value_missing",
        message=f"Unable to locate the Vault secret value for key: {key}.",
        status_code=404,
    )


def _vault_runtime_error(action: str, key: str, exc: Exception, status_code: int = 503) -> ApiError:
    return ApiError(
        error_code=f"vault_{action}_error",
        message=f"Could not {action} secret with key: {key}. Original error is: {exc}",
        status_code=status_code,
    )


class VaultMetadataRepository:
    """DB access for Vault secret metadata."""

    def generate_id(self) -> str:
        return uuid.uuid4().hex

    def build(
        self,
        name: str,
        user: UserModel,
        tenant_id: str,
        metadata_id: str | None = None,
    ) -> VaultMetadataModel:
        return VaultMetadataModel(
            id=metadata_id or self.generate_id(),
            name=name,
            user_id=user.id,
            created_by=user.username,
            modified_by=user.username,
            m8f_tenant_id=tenant_id,
        )

    def get_by_name(self, name: str, tenant_id: str) -> VaultMetadataModel:
        metadata = (
            VaultMetadataModel.query.filter(VaultMetadataModel.m8f_tenant_id == tenant_id)
            .filter(VaultMetadataModel.name == name)
            .first()
        )
        if isinstance(metadata, VaultMetadataModel):
            return metadata
        raise _secret_not_found(name)

    def get_optional_by_name(self, name: str, tenant_id: str) -> VaultMetadataModel | None:
        metadata = (
            VaultMetadataModel.query.filter(VaultMetadataModel.m8f_tenant_id == tenant_id)
            .filter(VaultMetadataModel.name == name)
            .first()
        )
        return metadata if isinstance(metadata, VaultMetadataModel) else None

    def delete(self, metadata: VaultMetadataModel) -> None:
        db.session.delete(metadata)

    def list_query(self):
        return VaultMetadataModel.query.order_by(VaultMetadataModel.name).join(UserModel).add_columns(UserModel.username)


class LegacyDatabaseSecretBackend:
    """Current database-backed secret storage."""

    def add_secret(self, key: str, value: str, user_id: int) -> "SecretModel":
        from spiffworkflow_backend.models.secret_model import SecretModel

        encrypted_value = _encrypt_secret_value(value)
        secret_model = SecretModel(key=key, value=encrypted_value, user_id=user_id)
        db.session.add(secret_model)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            raise ApiError(
                error_code="create_secret_error",
                message=f"There was an error creating a secret with key: {key}. Original error is {exc}",
            ) from exc
        return secret_model

    def get_secret(self, key: str) -> "SecretModel":
        from spiffworkflow_backend.models.secret_model import SecretModel

        secret = db.session.query(SecretModel).filter(SecretModel.key == key).first()
        if isinstance(secret, SecretModel):
            return secret
        raise _secret_not_found(key)

    def update_secret(
        self,
        key: str,
        value: str,
        user_id: int | None = None,
        create_if_not_exists: bool | None = False,
        new_key: str | None = None,
    ) -> None:
        secret_model = SecretModel.query.filter(SecretModel.key == key).first()
        if secret_model:
            secret_model.value = _encrypt_secret_value(value)
            if new_key:
                secret_model.key = new_key
            db.session.add(secret_model)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            return

        if create_if_not_exists:
            if user_id is None:
                raise ApiError(
                    error_code="update_secret_error_no_user_id",
                    message=f"Cannot update secret with key: {key}. Missing user id.",
                    status_code=404,
                )
            self.add_secret(key=key, value=value, user_id=user_id)
            return

        raise ApiError(
            error_code="update_secret_error",
            message=f"Cannot update secret with key: {key}. Resource does not exist.",
            status_code=404,
        )

    def delete_secret(self, key: str, user_id: int) -> None:
        secret_model = SecretModel.query.filter(SecretModel.key == key).first()
        if secret_model:
            db.session.delete(secret_model)
            try:
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                raise ApiError(
                    error_code="delete_secret_error",
                    message=f"Could not delete secret with key: {key}. Original error is: {exc}",
                ) from exc
            return

        raise ApiError(
            error_code="delete_secret_error",
            message=f"Cannot delete secret with key: {key}. Resource does not exist.",
            status_code=404,
        )

    def list_secrets(self, page: int = 1, per_page: int = 100, tenant_id: str | None = None):
        from spiffworkflow_backend.models.secret_model import SecretModel

        query = SecretModel.query.order_by(SecretModel.key).join(UserModel).add_columns(UserModel.username)
        if tenant_id:
            query = query.filter(SecretModel.m8f_tenant_id == tenant_id)
        return query.paginate(page=page, per_page=per_page, error_out=False)

    def serialize_secret_list_result(
        self,
        page: int = 1,
        per_page: int = 100,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        secrets = self.list_secrets(page=page, per_page=per_page, tenant_id=tenant_id)
        tenant_ids = {
            secret.m8f_tenant_id
            for secret, _username in secrets.items
            if isinstance(secret.m8f_tenant_id, str) and secret.m8f_tenant_id
        }
        tenant_name_by_id: dict[str, str] = {}
        if tenant_ids:
            tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
            tenant_name_by_id = {tenant.id: tenant.name for tenant in tenants}
        results = []
        for secret, username in secrets.items:
            row = secret.to_dict()
            row["username"] = username
            row["tenantId"] = secret.m8f_tenant_id
            row["tenantName"] = tenant_name_by_id.get(secret.m8f_tenant_id)
            results.append(row)
        return {
            "results": results,
            "pagination": {
                "count": len(secrets.items),
                "total": secrets.total,
                "pages": secrets.pages,
            },
        }

    def get_secret_value(self, key: str) -> str:
        from spiffworkflow_backend.services.secret_service import SecretService

        secret = self.get_secret(key)
        return SecretService._decrypt(secret.value)


class VaultBackedSecretBackend:
    """Vault storage with DB-only metadata."""

    def __init__(
        self,
        metadata_repository: VaultMetadataRepository | None = None,
        vault_client: VaultClient | None = None,
        user_lookup: Callable[[int], UserModel | None] | None = None,
    ) -> None:
        self._metadata_repository = metadata_repository or VaultMetadataRepository()
        self._vault_client = vault_client or get_vault_client()
        self._user_lookup = user_lookup or (lambda user_id: UserModel.query.filter_by(id=user_id).first())

    def add_secret(self, key: str, value: str, user_id: int) -> ResolvedSecret:
        user = self._require_user(user_id)
        tenant_id = self._require_current_tenant_id()
        if self._metadata_repository.get_optional_by_name(key, tenant_id=tenant_id) is not None:
            raise ApiError(
                error_code="create_secret_error",
                message=f"There was an error creating a secret with key: {key}. A secret with that key already exists.",
                status_code=409,
            )
        metadata = self._metadata_repository.build(key, user, tenant_id=tenant_id)
        path = self._vault_path(metadata.m8f_tenant_id, metadata.name)

        try:
            self._vault_client.store_secret(path, value)
        except VaultClientError as exc:
            raise _vault_runtime_error("create", key, exc) from exc

        db.session.add(metadata)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            try:
                self._vault_client.delete_secret(path)
            except Exception as cleanup_exc:
                logger.error(
                    "vault_secret_create_compensation_failed tenant_id=%s metadata_id=%s path=%s cleanup_error=%s",
                    metadata.m8f_tenant_id,
                    metadata.id,
                    path,
                    cleanup_exc,
                )
            raise ApiError(
                error_code="create_secret_error",
                message=f"There was an error creating a secret with key: {key}. Original error is {exc}",
            ) from exc

        return self._resolved_secret(metadata, value)

    def get_secret(self, key: str) -> ResolvedSecret:
        metadata = self._metadata_repository.get_by_name(key, tenant_id=self._require_current_tenant_id())
        path = self._vault_path(metadata.m8f_tenant_id, metadata.name)

        try:
            value = self._vault_client.retrieve_secret(path)
        except VaultClientError as exc:
            raise _vault_runtime_error("read", key, exc) from exc

        if value is None:
            raise _vault_secret_missing_value(key, metadata.m8f_tenant_id, metadata.id, path)

        return self._resolved_secret(metadata, value)

    def get_secret_value(self, key: str) -> str:
        return self._read_secret_value(
            self._metadata_repository.get_by_name(key, tenant_id=self._require_current_tenant_id())
        )

    def update_secret(
        self,
        key: str,
        value: str,
        user_id: int | None = None,
        create_if_not_exists: bool | None = False,
        new_key: str | None = None,
    ) -> None:
        metadata = self._metadata_repository.get_optional_by_name(
            key,
            tenant_id=self._require_current_tenant_id(),
        )
        if metadata is None:
            if create_if_not_exists:
                if user_id is None:
                    raise ApiError(
                        error_code="update_secret_error_no_user_id",
                        message=f"Cannot update secret with key: {key}. Missing user id.",
                        status_code=404,
                    )
                self.add_secret(key=key, value=value, user_id=user_id)
                return
            raise ApiError(
                error_code="update_secret_error",
                message=f"Cannot update secret with key: {key}. Resource does not exist.",
                status_code=404,
            )

        if new_key and new_key != metadata.name:
            if self._metadata_repository.get_optional_by_name(new_key, tenant_id=metadata.m8f_tenant_id) is not None:
                raise ApiError(
                    error_code="update_secret_error",
                    message=(
                        f"Cannot update secret with key: {key}. "
                        f"The target key '{new_key}' already exists in tenant '{metadata.m8f_tenant_id}'."
                    ),
                    status_code=409,
                )

        path = self._vault_path(metadata.m8f_tenant_id, metadata.name)
        target_key = new_key or metadata.name
        target_path = self._vault_path(metadata.m8f_tenant_id, target_key)
        renamed = target_path != path
        previous_value = self._read_secret_value(metadata)

        try:
            self._vault_client.store_secret(target_path, value)
            if renamed:
                self._vault_client.delete_secret(path)
        except VaultClientError as exc:
            raise _vault_runtime_error("update", key, exc) from exc

        if new_key:
            metadata.name = new_key
        if user_id is not None:
            user = self._require_user(user_id)
            metadata.user_id = user.id
            metadata.modified_by = user.username

        db.session.add(metadata)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            try:
                self._vault_client.store_secret(path, previous_value)
                if renamed:
                    self._vault_client.delete_secret(target_path)
            except Exception as cleanup_exc:
                logger.error(
                    "vault_secret_update_compensation_failed tenant_id=%s metadata_id=%s path=%s target_path=%s cleanup_error=%s",
                    metadata.m8f_tenant_id,
                    metadata.id,
                    path,
                    target_path,
                    cleanup_exc,
                )
            raise ApiError(
                error_code="vault_update_inconsistent_state",
                message=(
                    f"Secret '{key}' was updated in Vault, but metadata persistence failed for tenant "
                    f"'{metadata.m8f_tenant_id}' and metadata id '{metadata.id}'. Original error is: {exc}"
                ),
                status_code=500,
            ) from exc

    def delete_secret(self, key: str, user_id: int) -> None:
        metadata = self._metadata_repository.get_optional_by_name(
            key,
            tenant_id=self._require_current_tenant_id(),
        )
        if metadata is None:
            raise ApiError(
                error_code="delete_secret_error",
                message=f"Cannot delete secret with key: {key}. Resource does not exist.",
                status_code=404,
            )

        path = self._vault_path(metadata.m8f_tenant_id, metadata.name)

        try:
            deleted = self._vault_client.delete_secret(path)
        except VaultConnectionError as exc:
            raise _vault_runtime_error("delete", key, exc) from exc
        except VaultClientError as exc:
            raise _vault_runtime_error("delete", key, exc, status_code=500) from exc

        if not deleted:
            logger.warning(
                "vault_secret_delete_missing_value tenant_id=%s metadata_id=%s path=%s",
                metadata.m8f_tenant_id,
                metadata.id,
                path,
            )

        self._metadata_repository.delete(metadata)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            raise ApiError(
                error_code="vault_delete_inconsistent_state",
                message=(
                    f"Vault secret delete succeeded, but metadata deletion failed for tenant "
                    f"'{metadata.m8f_tenant_id}', metadata id '{metadata.id}', path '{path}'."
                ),
                status_code=500,
            ) from exc

    def list_secrets(self, page: int = 1, per_page: int = 100, tenant_id: str | None = None):
        query = self._metadata_repository.list_query()
        effective_tenant_id = tenant_id or current_tenant_id_or_none()
        if effective_tenant_id:
            query = query.filter(VaultMetadataModel.m8f_tenant_id == effective_tenant_id)
        return query.paginate(page=page, per_page=per_page, error_out=False)

    def serialize_secret_list_result(self, page: int = 1, per_page: int = 100, tenant_id: str | None = None) -> dict[str, Any]:
        secrets = self.list_secrets(page=page, per_page=per_page, tenant_id=tenant_id)

        tenant_name_by_id: dict[str, str] = {}
        tenant_ids = {
            metadata.m8f_tenant_id
            for metadata, _username in secrets.items
            if isinstance(metadata.m8f_tenant_id, str) and metadata.m8f_tenant_id
        }
        if tenant_ids:
            tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
            tenant_name_by_id = {tenant.id: tenant.name for tenant in tenants}

        results = []
        for metadata, username in secrets.items:
            row = metadata.to_dict()
            row["username"] = username
            row["tenantId"] = metadata.m8f_tenant_id
            row["tenantName"] = tenant_name_by_id.get(metadata.m8f_tenant_id)
            results.append(row)

        return {
            "results": results,
            "pagination": {
                "count": len(secrets.items),
                "total": secrets.total,
                "pages": secrets.pages,
            },
        }

    def _read_secret_value(self, metadata: VaultMetadataModel) -> str:
        path = self._vault_path(metadata.m8f_tenant_id, metadata.name)

        try:
            value = self._vault_client.retrieve_secret(path)
        except VaultClientError as exc:
            raise _vault_runtime_error("read", metadata.name, exc) from exc

        if value is None:
            raise _vault_secret_missing_value(metadata.name, metadata.m8f_tenant_id, metadata.id, path)

        return value

    def _resolved_secret(self, metadata: VaultMetadataModel, value: str) -> ResolvedSecret:
        return ResolvedSecret(
            id=metadata.id,
            key=metadata.name,
            user_id=metadata.user_id,
            value=_encrypt_secret_value(value),
            updated_at_in_seconds=metadata.updated_at_in_seconds,
            created_at_in_seconds=metadata.created_at_in_seconds,
            m8f_tenant_id=metadata.m8f_tenant_id,
        )

    def _require_user(self, user_id: int) -> UserModel:
        user = self._user_lookup(user_id)
        if isinstance(user, UserModel):
            return user
        raise ApiError(
            error_code="missing_user_error",
            message=f"Unable to locate the user creating or updating secret metadata (user_id={user_id}).",
            status_code=404,
        )

    @staticmethod
    def _require_current_tenant_id() -> str:
        tenant_id = current_tenant_id_or_none()
        if isinstance(tenant_id, str) and tenant_id.strip():
            return tenant_id.strip()
        raise RuntimeError("Missing tenant context for Vault-backed secret operation.")

    @staticmethod
    def _vault_path(tenant_id: str, secret_name: str) -> str:
        prefix = str(current_app.config.get("M8FLOW_VAULT_SECRET_PATH_PREFIX") or "m8flow").strip().strip("/")
        normalized_secret_name = str(secret_name or "").strip().strip("/")
        if not normalized_secret_name:
            raise ValueError("secret_name must not be empty.")
        return f"{prefix}/tenants/{tenant_id}/secrets/{normalized_secret_name}"


def get_secret_backend() -> LegacyDatabaseSecretBackend | VaultBackedSecretBackend:
    backend_kind = current_app.config.get("M8FLOW_SECRET_BACKEND_KIND")
    if backend_kind == "vault" or (backend_kind is None and vault_enabled()):
        return VaultBackedSecretBackend()
    return LegacyDatabaseSecretBackend()
