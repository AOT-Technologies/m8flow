"""HashiCorp Vault KV v2 SecretProvider — tenant-scoped via AppRole."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from m8flow_backend.errors import ApiError
from m8flow_backend.secrets.http import HttpVault, VaultTransportError
from m8flow_backend.secrets.paths import (
    configuration_variable_path,
    connector_configuration_path,
    secret_path,
    secret_root,
)
from m8flow_backend.secrets.provider import SecretListPage, SecretRecord
from m8flow_backend.secrets.provisioning import (
    TenantVaultProvisioningError,
    request_tenant_identity,
)
from m8flow_backend.secrets.tenant_store_cache import (
    TENANT_STORES_INITIALIZING as _TENANT_STORES_INITIALIZING,
    TENANT_STORE_CACHE as _TENANT_STORE_CACHE,
    TENANT_STORE_CACHE_CONDITION as _TENANT_STORE_CACHE_CONDITION,
    invalidate_tenant_store_cache,  # noqa: F401 - re-exported for compatibility
)

LOGGER = logging.getLogger(__name__)

VaultStore = Any

_TENANT_STORE_CACHE_MAX_SIZE = 256


def _monotonic() -> float:
    return time.monotonic()


def _evict_rejected_tenant_store(tenant_id: str, rejected_store: VaultStore) -> None:
    """Evict only the rejected client, never a newer replacement."""
    with _TENANT_STORE_CACHE_CONDITION:
        for cache_key, (store, _deadline) in tuple(_TENANT_STORE_CACHE.items()):
            if cache_key[1] == tenant_id and store is rejected_store:
                _TENANT_STORE_CACHE.pop(cache_key, None)
                return


def _refresh_rejected_tenant_store(tenant_id: str, rejected_store: VaultStore) -> VaultStore:
    _evict_rejected_tenant_store(tenant_id, rejected_store)
    return _tenant_store(HttpVault.from_env(), tenant_id)


def _tenant_store(broker: HttpVault, tenant_id: str) -> VaultStore:
    cache_key = (broker.cache_identity, tenant_id)
    with _TENANT_STORE_CACHE_CONDITION:
        while True:
            cached = _TENANT_STORE_CACHE.get(cache_key)
            if cached is not None:
                store, deadline = cached
                if deadline > _monotonic():
                    _TENANT_STORE_CACHE.move_to_end(cache_key)
                    return store
                _TENANT_STORE_CACHE.pop(cache_key, None)
            if cache_key not in _TENANT_STORES_INITIALIZING:
                _TENANT_STORES_INITIALIZING.add(cache_key)
                break
            _TENANT_STORE_CACHE_CONDITION.wait()

    try:
        # Concurrent misses for this tenant share one login, while misses for
        # other tenants proceed independently.
        identity = request_tenant_identity(tenant_id)
        store = broker.store_for_tenant(
            tenant_id, role_name=identity.role_name, role_id=identity.role_id
        )
        set_auth_failure_callback = getattr(store, "set_auth_failure_callback", None)
        if callable(set_auth_failure_callback):
            set_auth_failure_callback(
                lambda rejected_store: _refresh_rejected_tenant_store(
                    tenant_id, rejected_store
                )
            )
        deadline = getattr(store, "token_cache_deadline", None)
    except BaseException:
        with _TENANT_STORE_CACHE_CONDITION:
            _TENANT_STORES_INITIALIZING.discard(cache_key)
            _TENANT_STORE_CACHE_CONDITION.notify_all()
        raise

    with _TENANT_STORE_CACHE_CONDITION:
        if isinstance(deadline, (int, float)) and deadline > _monotonic():
            _TENANT_STORE_CACHE[cache_key] = (store, float(deadline))
            _TENANT_STORE_CACHE.move_to_end(cache_key)
            while len(_TENANT_STORE_CACHE) > _TENANT_STORE_CACHE_MAX_SIZE:
                _TENANT_STORE_CACHE.popitem(last=False)
        _TENANT_STORES_INITIALIZING.discard(cache_key)
        _TENANT_STORE_CACHE_CONDITION.notify_all()
        return store


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
    created_raw = document.get("created_at")
    updated_raw = document.get("updated_at")
    created = datetime.fromisoformat(str(created_raw)) if created_raw else None
    updated = datetime.fromisoformat(str(updated_raw)) if updated_raw else None
    return SecretRecord(
        id=str(document.get("id") or key),
        key=key,
        user_id=user_id_int,
        tenant_id=str(document.get("tenant_id") or tenant_id),
        created_at=created,
        updated_at=updated,
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
            # Reconcile and mint a tenant token only on cache miss/expiry.
            # Secret operations then use the cached, tenant-scoped token and
            # do not require broker control-plane access on every request.
            return _tenant_store(broker, tenant_id)
        except (VaultTransportError, TenantVaultProvisioningError) as exc:
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
            now = datetime.now(timezone.utc)
            username = _username(session, user_id)
            document: dict[str, object] = {
                "id": uuid.uuid4().hex,
                "key": key,
                "value": value,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "username": username,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
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
        document["updated_at"] = datetime.now(timezone.utc).isoformat()
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
            # New structured provider documents live in subfolders under the
            # root and are not ordinary named secrets in the legacy UI.
            return [
                key
                for key in self._kv(tenant_id).list_names(secret_root(tenant_id))
                if key not in {"configuration-variable", "connector-configuration"}
            ]
        except ApiError:
            raise
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message="Could not list secrets.",
                status_code=503,
            ) from exc

    def set_configuration_value(
        self,
        session: Any,
        *,
        tenant_id: str,
        variable_id: str,
        value: str,
        user_id: int,
    ) -> None:
        del session, user_id
        try:
            self._kv(tenant_id).put_document(
                configuration_variable_path(tenant_id, variable_id), {"value": value}
            )
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message="Could not store the configuration variable.",
                status_code=503,
            ) from exc

    def get_configuration_value(
        self, session: Any, *, tenant_id: str, variable_id: str
    ) -> str | None:
        del session
        try:
            document = self._kv(tenant_id).get_document(
                configuration_variable_path(tenant_id, variable_id)
            )
            if document is None:
                return None
            value = document.get("value")
            return value if isinstance(value, str) else None
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message="Could not read the configuration variable.",
                status_code=503,
            ) from exc

    def delete_configuration_value(
        self, session: Any, *, tenant_id: str, variable_id: str
    ) -> None:
        del session
        try:
            self._kv(tenant_id).delete_document(
                configuration_variable_path(tenant_id, variable_id)
            )
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message="Could not delete the configuration variable.",
                status_code=503,
            ) from exc

    def set_connector_configuration(
        self,
        session: Any,
        *,
        tenant_id: str,
        configuration_id: int | str,
        values: dict[str, str],
        user_id: int,
        replace_existing: bool,
    ) -> None:
        del session, user_id
        path = connector_configuration_path(tenant_id, configuration_id)
        try:
            store = self._kv(tenant_id)
            versioned_get = getattr(store, "get_versioned_document", None)
            if callable(versioned_get):
                current, version = versioned_get(path)
            else:
                current = store.get_document(path)
                version = None
            if current is not None and current != values and not replace_existing:
                raise ApiError(
                    "secret_storage_conflict",
                    "A different connector secret document already exists at the profile path.",
                    409,
                )
            if current == values:
                return

            if callable(versioned_get):
                store.put_document(path, values, cas=version or 0)
            else:
                store.put_document(path, values)
            if store.get_document(path) != values:
                raise VaultTransportError("Connector secret document verification failed.")
        except ApiError:
            raise
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message="Could not store the connector configuration.",
                status_code=503,
            ) from exc

    def get_connector_configuration(
        self, session: Any, *, tenant_id: str, configuration_id: int | str
    ) -> dict[str, str] | None:
        del session
        try:
            document = self._kv(tenant_id).get_document(
                connector_configuration_path(tenant_id, configuration_id)
            )
            if document is None:
                return None
            if any(
                not isinstance(name, str) or not isinstance(value, str)
                for name, value in document.items()
            ):
                raise VaultTransportError("Connector secret document has an invalid shape.")
            return {str(name): str(value) for name, value in document.items()}
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message="Could not read the connector configuration.",
                status_code=503,
            ) from exc

    def delete_connector_configuration(
        self, session: Any, *, tenant_id: str, configuration_id: int | str
    ) -> None:
        del session
        try:
            self._kv(tenant_id).delete_document(
                connector_configuration_path(tenant_id, configuration_id)
            )
        except Exception as exc:
            raise _wrap(
                exc,
                error_code="vault_unavailable",
                message="Could not delete the connector configuration.",
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
        from m8flow_core.models.user import UserModel

        user = getter(UserModel, user_id)
    except Exception:
        return None
    return getattr(user, "username", None)
