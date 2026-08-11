from __future__ import annotations

from dataclasses import dataclass
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Callable

from flask import current_app

from m8flow_backend.config import vault_enabled
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.services.secret_backend_contract import SecretBackend
from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.services.tenant_scoped_vault_client_provider import (
    TenantScopedVaultClientError,
    TenantScopedVaultClientProvider,
)
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
_VAULT_SECRET_ID_FIELD = "id"
_VAULT_SECRET_KEY_FIELD = "key"
_VAULT_SECRET_TENANT_ID_FIELD = "tenant_id"
_VAULT_SECRET_USER_ID_FIELD = "user_id"
_VAULT_SECRET_USERNAME_FIELD = "username"
_VAULT_SECRET_VALUE_FIELD = "value"
_VAULT_SECRET_CREATED_AT_FIELD = "created_at_in_seconds"
_VAULT_SECRET_UPDATED_AT_FIELD = "updated_at_in_seconds"


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


@dataclass(frozen=True)
class VaultSecretRecord:
    """Vault-native secret document used to rebuild API responses without SQL metadata."""

    id: str
    key: str
    user_id: int
    username: str | None
    tenant_id: str
    value: str | None
    updated_at_in_seconds: int | None
    created_at_in_seconds: int | None

    def to_vault_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            _VAULT_SECRET_ID_FIELD: self.id,
            _VAULT_SECRET_KEY_FIELD: self.key,
            _VAULT_SECRET_TENANT_ID_FIELD: self.tenant_id,
            _VAULT_SECRET_USER_ID_FIELD: self.user_id,
            _VAULT_SECRET_CREATED_AT_FIELD: self.created_at_in_seconds,
            _VAULT_SECRET_UPDATED_AT_FIELD: self.updated_at_in_seconds,
        }
        if self.username is not None:
            document[_VAULT_SECRET_USERNAME_FIELD] = self.username
        if self.value is not None:
            document[_VAULT_SECRET_VALUE_FIELD] = self.value
        return document


def _encrypt_secret_value(value: str) -> str:
    from spiffworkflow_backend.services.secret_service import SecretService

    return SecretService._encrypt(value)


def _secret_not_found(key: str) -> ApiError:
    return ApiError(
        error_code="missing_secret_error",
        message=f"Unable to locate a secret with the name: {key}. ",
        status_code=404,
    )


def _vault_secret_missing_value(key: str, tenant_id: str, secret_id: str, path: str) -> ApiError:
    logger.warning(
        "vault_secret_value_missing tenant_id=%s secret_id=%s key=%s path=%s",
        tenant_id,
        secret_id,
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
    """Vault storage with Vault-native metadata documents."""

    def __init__(
        self,
        vault_client: VaultClient | None = None,
        tenant_vault_client_provider: TenantScopedVaultClientProvider | None = None,
        user_lookup: Callable[[int], UserModel | None] | None = None,
    ) -> None:
        self._broker_vault_client = vault_client or get_vault_client()
        self._tenant_vault_client_provider = tenant_vault_client_provider or TenantScopedVaultClientProvider(
            broker_vault_client=self._broker_vault_client
        )
        self._user_lookup = user_lookup or (lambda user_id: UserModel.query.filter_by(id=user_id).first())

    def add_secret(self, key: str, value: str, user_id: int) -> ResolvedSecret:
        user = self._require_user(user_id)
        tenant_id = self._require_current_tenant_id()
        vault_client = self._require_tenant_vault_client(tenant_id=tenant_id, action="create", key=key)
        existing = self._get_optional_secret_record(
            key=key,
            tenant_id=tenant_id,
            action="create",
            vault_client=vault_client,
        )
        if existing is not None:
            raise ApiError(
                error_code="create_secret_error",
                message=f"There was an error creating a secret with key: {key}. A secret with that key already exists.",
                status_code=409,
            )

        now = round(time.time())
        record = VaultSecretRecord(
            id=uuid.uuid4().hex,
            key=key,
            user_id=user.id,
            username=user.username,
            tenant_id=tenant_id,
            value=value,
            updated_at_in_seconds=now,
            created_at_in_seconds=now,
        )
        path = self._vault_path(tenant_id, key)

        try:
            vault_client.store_secret_document(path, record.to_vault_document())
        except VaultClientError as exc:
            raise _vault_runtime_error("create", key, exc) from exc

        return self._resolved_secret(record)

    def get_secret(self, key: str) -> ResolvedSecret:
        tenant_id = self._require_current_tenant_id()
        vault_client = self._require_tenant_vault_client(tenant_id=tenant_id, action="read", key=key)
        record = self._require_secret_record(
            key=key,
            tenant_id=tenant_id,
            vault_client=vault_client,
        )
        if record.value is None:
            raise _vault_secret_missing_value(key, tenant_id, record.id, self._vault_path(tenant_id, key))
        return self._resolved_secret(record)

    def get_secret_value(self, key: str) -> str:
        tenant_id = self._require_current_tenant_id()
        vault_client = self._require_tenant_vault_client(tenant_id=tenant_id, action="read", key=key)
        record = self._require_secret_record(
            key=key,
            tenant_id=tenant_id,
            vault_client=vault_client,
        )
        if record.value is None:
            raise _vault_secret_missing_value(key, tenant_id, record.id, self._vault_path(tenant_id, key))
        return record.value

    def update_secret(
        self,
        key: str,
        value: str,
        user_id: int | None = None,
        create_if_not_exists: bool | None = False,
        new_key: str | None = None,
    ) -> None:
        tenant_id = self._require_current_tenant_id()
        vault_client = self._require_tenant_vault_client(tenant_id=tenant_id, action="update", key=key)
        existing = self._get_optional_secret_record(
            key=key,
            tenant_id=tenant_id,
            action="update",
            vault_client=vault_client,
        )
        if existing is None:
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

        normalized_new_key = str(new_key or "").strip() or None
        target_key = normalized_new_key or existing.key
        if target_key != existing.key:
            target_existing = self._get_optional_secret_record(
                key=target_key,
                tenant_id=tenant_id,
                action="update",
                vault_client=vault_client,
            )
            if target_existing is not None:
                raise ApiError(
                    error_code="update_secret_error",
                    message=(
                        f"Cannot update secret with key: {key}. "
                        f"The target key '{target_key}' already exists in tenant '{tenant_id}'."
                    ),
                    status_code=409,
                )

        actor = self._require_user(user_id) if user_id is not None else None
        now = round(time.time())
        updated_record = VaultSecretRecord(
            id=existing.id,
            key=target_key,
            user_id=actor.id if actor is not None else existing.user_id,
            username=actor.username if actor is not None else existing.username,
            tenant_id=tenant_id,
            value=value,
            updated_at_in_seconds=now,
            created_at_in_seconds=existing.created_at_in_seconds or now,
        )

        path = self._vault_path(tenant_id, existing.key)
        target_path = self._vault_path(tenant_id, target_key)
        renamed = target_path != path

        try:
            vault_client.store_secret_document(target_path, updated_record.to_vault_document())
            if renamed:
                vault_client.delete_secret(path)
        except VaultClientError as exc:
            if renamed:
                try:
                    vault_client.delete_secret(target_path)
                except Exception as cleanup_exc:
                    logger.error(
                        "vault_secret_update_compensation_failed tenant_id=%s secret_id=%s path=%s target_path=%s cleanup_error=%s",
                        tenant_id,
                        existing.id,
                        path,
                        target_path,
                        cleanup_exc,
                    )
            raise _vault_runtime_error("update", key, exc) from exc

    def delete_secret(self, key: str, user_id: int) -> None:
        del user_id
        tenant_id = self._require_current_tenant_id()
        vault_client = self._require_tenant_vault_client(tenant_id=tenant_id, action="delete", key=key)
        existing = self._get_optional_secret_record(
            key=key,
            tenant_id=tenant_id,
            action="delete",
            vault_client=vault_client,
        )
        if existing is None:
            raise ApiError(
                error_code="delete_secret_error",
                message=f"Cannot delete secret with key: {key}. Resource does not exist.",
                status_code=404,
            )

        path = self._vault_path(tenant_id, key)

        try:
            deleted = vault_client.delete_secret(path)
        except VaultConnectionError as exc:
            raise _vault_runtime_error("delete", key, exc) from exc
        except VaultClientError as exc:
            raise _vault_runtime_error("delete", key, exc, status_code=500) from exc

        if not deleted:
            logger.warning(
                "vault_secret_delete_missing_value tenant_id=%s secret_id=%s path=%s",
                tenant_id,
                existing.id,
                path,
            )

    def list_secrets(self, page: int = 1, per_page: int = 100, tenant_id: str | None = None) -> list[VaultSecretRecord]:
        del page
        del per_page
        effective_tenant_id = tenant_id or current_tenant_id_or_none()
        return self._list_secret_records(effective_tenant_id)

    def serialize_secret_list_result(
        self,
        page: int = 1,
        per_page: int = 100,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        records = self.list_secrets(page=page, per_page=per_page, tenant_id=tenant_id)
        normalized_page = max(page, 1)
        normalized_per_page = max(per_page, 1)
        start = (normalized_page - 1) * normalized_per_page
        paged_records = records[start : start + normalized_per_page]
        total = len(records)

        tenant_ids = {record.tenant_id for record in paged_records if record.tenant_id}
        tenant_name_by_id: dict[str, str] = {}
        if tenant_ids:
            tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
            tenant_name_by_id = {tenant.id: tenant.name for tenant in tenants}

        results = []
        for record in paged_records:
            row = {
                "id": record.id,
                "key": record.key,
                "user_id": record.user_id,
                "updated_at_in_seconds": record.updated_at_in_seconds,
                "created_at_in_seconds": record.created_at_in_seconds,
                "username": record.username,
                "tenantId": record.tenant_id,
                "tenantName": tenant_name_by_id.get(record.tenant_id),
            }
            results.append(row)

        return {
            "results": results,
            "pagination": {
                "count": len(paged_records),
                "total": total,
                "pages": (total + normalized_per_page - 1) // normalized_per_page if total else 0,
            },
        }

    def _list_secret_records(self, tenant_id: str | None) -> list[VaultSecretRecord]:
        if tenant_id:
            records = self._list_secret_records_for_tenant(tenant_id)
        else:
            records = []
            for discovered_tenant_id in self._list_tenant_ids():
                records.extend(self._list_secret_records_for_tenant(discovered_tenant_id))

        return sorted(
            records,
            key=lambda record: (record.key.casefold(), record.tenant_id.casefold(), record.id),
        )

    def _list_tenant_ids(self) -> list[str]:
        tenants = M8flowTenantModel.query.order_by(M8flowTenantModel.id).all()
        tenant_ids = {
            tenant.id.strip()
            for tenant in tenants
            if isinstance(tenant.id, str) and tenant.id.strip()
        }
        return sorted(tenant_ids)

    def _list_secret_records_for_tenant(self, tenant_id: str) -> list[VaultSecretRecord]:
        root_path = self._vault_secret_root(tenant_id)
        records: list[VaultSecretRecord] = []
        vault_client = self._require_tenant_vault_client(tenant_id=tenant_id, action="list", key=tenant_id)
        for secret_path in self._list_secret_paths(
            root_path=root_path,
            error_key=tenant_id,
            vault_client=vault_client,
        ):
            secret_name = self._secret_name_from_path(secret_path, tenant_id)
            record = self._get_record_from_path(
                path=secret_path,
                secret_name=secret_name,
                tenant_id=tenant_id,
                action="list",
                vault_client=vault_client,
            )
            if record is not None:
                records.append(record)
        return records

    def _list_secret_paths(self, root_path: str, error_key: str, vault_client: VaultClient) -> list[str]:
        try:
            entries = vault_client.list_secret_names(root_path)
        except VaultClientError as exc:
            raise _vault_runtime_error("list", error_key, exc) from exc

        secret_paths: list[str] = []
        for entry in entries:
            normalized_entry = entry.strip().strip("/")
            if not normalized_entry:
                continue
            next_path = f"{root_path}/{normalized_entry}"
            if entry.endswith("/"):
                secret_paths.extend(
                    self._list_secret_paths(
                        root_path=next_path,
                        error_key=error_key,
                        vault_client=vault_client,
                    )
                )
            else:
                secret_paths.append(next_path)
        return secret_paths

    def _require_secret_record(self, key: str, tenant_id: str, vault_client: VaultClient) -> VaultSecretRecord:
        record = self._get_optional_secret_record(
            key=key,
            tenant_id=tenant_id,
            action="read",
            vault_client=vault_client,
        )
        if record is not None:
            return record
        raise _secret_not_found(key)

    def _get_optional_secret_record(
        self,
        key: str,
        tenant_id: str,
        action: str,
        vault_client: VaultClient,
    ) -> VaultSecretRecord | None:
        return self._get_record_from_path(
            path=self._vault_path(tenant_id, key),
            secret_name=key,
            tenant_id=tenant_id,
            action=action,
            vault_client=vault_client,
        )

    def _get_record_from_path(
        self,
        path: str,
        secret_name: str,
        tenant_id: str,
        action: str,
        vault_client: VaultClient,
    ) -> VaultSecretRecord | None:
        try:
            document = vault_client.retrieve_secret_document(path)
        except VaultClientError as exc:
            raise _vault_runtime_error(action, secret_name, exc) from exc

        if document is None:
            return None

        return self._record_from_document(
            path=path,
            secret_name=secret_name,
            tenant_id=tenant_id,
            document=document,
        )

    def _record_from_document(
        self,
        path: str,
        secret_name: str,
        tenant_id: str,
        document: dict[str, Any],
    ) -> VaultSecretRecord:
        user_id = self._coerce_int(document.get(_VAULT_SECRET_USER_ID_FIELD)) or 0
        username = self._normalize_username(document.get(_VAULT_SECRET_USERNAME_FIELD))
        if username is None and user_id > 0:
            user = self._user_lookup(user_id)
            if isinstance(user, UserModel):
                username = user.username

        created_at = self._coerce_int(document.get(_VAULT_SECRET_CREATED_AT_FIELD))
        updated_at = self._coerce_int(document.get(_VAULT_SECRET_UPDATED_AT_FIELD))
        value = document.get(_VAULT_SECRET_VALUE_FIELD)

        return VaultSecretRecord(
            id=str(document.get(_VAULT_SECRET_ID_FIELD) or uuid.uuid5(uuid.NAMESPACE_URL, path).hex),
            key=secret_name,
            user_id=user_id,
            username=username,
            tenant_id=tenant_id,
            value=None if value is None else str(value),
            updated_at_in_seconds=updated_at or created_at,
            created_at_in_seconds=created_at or updated_at,
        )

    def _resolved_secret(self, record: VaultSecretRecord) -> ResolvedSecret:
        if record.value is None:
            raise ValueError("Vault secret record is missing a secret value.")
        return ResolvedSecret(
            id=record.id,
            key=record.key,
            user_id=record.user_id,
            value=_encrypt_secret_value(record.value),
            updated_at_in_seconds=record.updated_at_in_seconds,
            created_at_in_seconds=record.created_at_in_seconds,
            m8f_tenant_id=record.tenant_id,
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
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_username(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _require_tenant_vault_client(self, tenant_id: str, action: str, key: str) -> VaultClient:
        try:
            scoped_client = self._tenant_vault_client_provider.for_tenant(tenant_id)
        except TenantScopedVaultClientError as exc:
            raise _vault_runtime_error(action, key, exc) from exc
        return scoped_client.vault_client

    @staticmethod
    def _require_current_tenant_id() -> str:
        tenant_id = current_tenant_id_or_none()
        if isinstance(tenant_id, str) and tenant_id.strip():
            return tenant_id.strip()
        raise RuntimeError("Missing tenant context for Vault-backed secret operation.")

    @staticmethod
    def _join_vault_path(*parts: str) -> str:
        normalized_parts = [part.strip().strip("/") for part in parts if part and part.strip().strip("/")]
        return "/".join(normalized_parts)

    @classmethod
    def _vault_tenants_root(cls) -> str:
        prefix = str(current_app.config.get("M8FLOW_VAULT_SECRET_PATH_PREFIX") or "m8flow").strip().strip("/")
        return cls._join_vault_path(prefix, "tenants")

    @classmethod
    def _vault_secret_root(cls, tenant_id: str) -> str:
        return cls._join_vault_path(cls._vault_tenants_root(), tenant_id, "secrets")

    @classmethod
    def _vault_path(cls, tenant_id: str, secret_name: str) -> str:
        normalized_secret_name = str(secret_name or "").strip().strip("/")
        if not normalized_secret_name:
            raise ValueError("secret_name must not be empty.")
        return cls._join_vault_path(cls._vault_secret_root(tenant_id), normalized_secret_name)

    @classmethod
    def _secret_name_from_path(cls, path: str, tenant_id: str) -> str:
        root = f"{cls._vault_secret_root(tenant_id)}/"
        return path[len(root) :] if path.startswith(root) else path.rsplit("/", 1)[-1]


def get_secret_backend() -> SecretBackend:
    backend_kind = current_app.config.get("M8FLOW_SECRET_BACKEND_KIND")
    if backend_kind == "vault" or (backend_kind is None and vault_enabled()):
        return VaultBackedSecretBackend()
    return LegacyDatabaseSecretBackend()
