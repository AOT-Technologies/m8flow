"""HashiCorp Vault KV v2 SecretProvider — tenant-scoped via AppRole."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from m8flow_backend.errors import ApiError
from m8flow_backend.secrets.http import HttpVault, VaultTransportError
from m8flow_backend.secrets.paths import secret_path, secret_root
from m8flow_backend.secrets.provider import SecretListPage, SecretRecord
from m8flow_backend.secrets.provisioning import tenant_role_name

LOGGER = logging.getLogger(__name__)

VaultStore = Any


def _not_found(key: str) -> ApiError:
    return ApiError(
        "missing_secret_error",
        f"Unable to locate a secret with the name: {key}. ",
        404,
    )


def _wrap(exc: Exception, *, error_code: str, message: str, status_code: int) -> ApiError:
    LOGGER.warning("%s: %s", error_code, type(exc).__name__)
    return ApiError(error_code, message, status_code)


def _record_from_document(document: dict[str, object], *, key: str, tenant_id: str) -> SecretRecord:
    user_id = document.get("user_id") or 0
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        user_id_int = 0
    created = document.get("created_at_in_seconds")
    updated = document.get("updated_at_in_seconds")
    return SecretRecord(
        id=str(document.get("id") or key),
        key=key,
        user_id=user_id_int,
        tenant_id=str(document.get("tenant_id") or tenant_id),
        created_at_in_seconds=int(created) if created else None,
        updated_at_in_seconds=int(updated) if updated else None,
    )


class VaultSecretProvider:
    def __init__(
        self,
        *,
        store: VaultStore | None = None,
        store_for_tenant: Callable[[str], VaultStore] | None = None,
    ) -> None:
        self._store = store
        self._store_for_tenant = store_for_tenant

    def _kv(self, tenant_id: str) -> VaultStore:
        if self._store_for_tenant is not None:
            return self._store_for_tenant(tenant_id)
        if self._store is not None:
            return self._store
        try:
            broker = HttpVault.from_env()
            return broker.store_for_tenant(tenant_id, role_name=tenant_role_name(tenant_id))
        except VaultTransportError as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message="Vault is down.",
                status_code=503,
            ) from exc

    def add(self, session: Any, *, tenant_id: str, key: str, value: str, user_id: int) -> SecretRecord:
        kv = self._kv(tenant_id)
        path = secret_path(tenant_id, key)
        try:
            if kv.get_document(path) is not None:
                raise ApiError(
                    "create_secret_error",
                    f"There was an error creating a secret with key: {key}.",
                    409,
                )
            now = int(time.time())
            username = _username(session, user_id)
            document: dict[str, object] = {
                "id": uuid.uuid4().hex,
                "key": key,
                "value": value,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "username": username,
                "created_at_in_seconds": now,
                "updated_at_in_seconds": now,
            }
            kv.put_document(path, document)
        except ApiError:
            raise
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message=f"Could not create secret with key: {key}.",
                status_code=503,
            ) from exc
        return _record_from_document(document, key=key, tenant_id=tenant_id)

    def get(self, session: Any, *, tenant_id: str, key: str) -> SecretRecord:
        document = self._read(tenant_id, key, missing_ok=False)
        return _record_from_document(document, key=key, tenant_id=tenant_id)

    def get_value(self, session: Any, *, tenant_id: str, key: str) -> str | None:
        document = self._read(tenant_id, key, missing_ok=True)
        if document is None:
            return None
        value = document.get("value")
        return None if value is None else str(value)

    def update(self, session: Any, *, tenant_id: str, key: str, value: str) -> None:
        document = self._read(tenant_id, key, missing_ok=False, error_code="update_secret_error")
        document["value"] = value
        document["updated_at_in_seconds"] = int(time.time())
        try:
            self._kv(tenant_id).put_document(secret_path(tenant_id, key), document)
        except ApiError:
            raise
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message=f"Could not update secret with key: {key}.",
                status_code=503,
            ) from exc

    def delete(self, session: Any, *, tenant_id: str, key: str) -> None:
        self._read(tenant_id, key, missing_ok=False, error_code="delete_secret_error")
        try:
            self._kv(tenant_id).delete_document(secret_path(tenant_id, key))
        except ApiError:
            raise
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message=f"Could not delete secret with key: {key}.",
                status_code=503,
            ) from exc

    def list(self, session: Any, *, tenant_id: str, page: int = 1, per_page: int = 100) -> SecretListPage:
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        keys = self.list_keys(session, tenant_id=tenant_id)
        total = len(keys)
        window = keys[(page - 1) * per_page : page * per_page]
        records = []
        for key in window:
            document = self._read(tenant_id, key, missing_ok=True)
            if document is None:
                continue
            records.append(_record_from_document(document, key=key, tenant_id=tenant_id))
        return SecretListPage(records=tuple(records), total=total, page=page, per_page=per_page)

    def list_keys(self, session: Any, *, tenant_id: str) -> list[str]:
        try:
            return self._kv(tenant_id).list_names(secret_root(tenant_id))
        except ApiError:
            raise
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message="Could not list secrets.",
                status_code=503,
            ) from exc

    def _read(
        self,
        tenant_id: str,
        key: str,
        *,
        missing_ok: bool,
        error_code: str = "missing_secret_error",
    ) -> dict[str, object] | None:
        try:
            document = self._kv(tenant_id).get_document(secret_path(tenant_id, key))
        except ApiError:
            raise
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message=f"Could not read secret with key: {key}.",
                status_code=503,
            ) from exc
        if document is None:
            if missing_ok:
                return None
            if error_code == "missing_secret_error":
                raise _not_found(key)
            raise ApiError(
                error_code,
                f"Cannot {'update' if error_code == 'update_secret_error' else 'delete'} secret with key: {key}. Resource does not exist.",
                404,
            )
        return document


def _username(session: Any, user_id: int) -> str | None:
    if session is None or not user_id:
        return None
    getter = getattr(session, "get", None)
    if getter is None:
        return None
    try:
        from m8flow_bpmn_core.models.user import UserModel

        user = getter(UserModel, user_id)
    except Exception:
        return None
    return getattr(user, "username", None)
