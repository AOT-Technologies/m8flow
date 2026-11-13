"""HashiCorp Vault KV v2 + AppRole HTTP adapter.

Talks to Vault over ``requests``. Tests inject in-memory stores instead of this
adapter, so the provider never needs a live Vault process.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

import requests

from m8flow_backend.config import (
    vault_addr,
    vault_approle_mount_point,
    vault_mount_point,
    vault_namespace,
    vault_role_id,
    vault_secret_id,
    vault_timeout_seconds,
    vault_token,
    vault_verify,
)


class VaultTransportError(RuntimeError):
    """Vault HTTP failed. Callers must not put ``str(self)`` on API responses."""


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppRoleSecret:
    secret_id: str
    secret_id_accessor: str | None = None


def _lease_duration(auth: dict[str, Any]) -> int | None:
    if not isinstance(auth, dict):
        return None
    raw = auth.get("lease_duration")
    try:
        duration = int(raw)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def _token_expiry(auth: dict[str, Any]) -> float | None:
    duration = _lease_duration(auth)
    return time.monotonic() + duration if duration is not None else None


class HttpVault:
    def __init__(
        self,
        *,
        addr: str,
        token: str | None = None,
        namespace: str | None = None,
        mount: str = "kv",
        approle_mount: str = "approle",
        timeout_seconds: float = 5.0,
        verify: bool | str = True,
        role_id: str | None = None,
        secret_id: str | None = None,
        token_expires_at: float | None = None,
        token_lease_duration: int | None = None,
    ) -> None:
        self._addr = addr.rstrip("/")
        self._token = token
        self._namespace = namespace
        self._mount = mount.strip().strip("/")
        self._approle_mount = approle_mount.strip().strip("/")
        self._timeout = timeout_seconds
        self._verify = verify
        self._role_id = role_id
        self._secret_id = secret_id
        self._token_expires_at = token_expires_at
        self._token_lease_duration = token_lease_duration
        self._auth_failure_callback: Callable[[HttpVault], HttpVault] | None = None

    @property
    def cache_identity(self) -> tuple[str, str | None, str, str, bool | str]:
        """Connection settings that determine whether a cached tenant client is reusable."""
        return (self._addr, self._namespace, self._mount, self._approle_mount, self._verify)

    @property
    def token_cache_deadline(self) -> float | None:
        """Return a conservative monotonic deadline for reuse of this client."""
        if self._token_expires_at is None or self._token_lease_duration is None:
            return None
        skew = min(30.0, max(1.0, self._token_lease_duration * 0.1))
        return self._token_expires_at - skew

    def set_auth_failure_callback(
        self, callback: Callable[[HttpVault], HttpVault]
    ) -> None:
        """Register a one-time refresh for a rejected token or stale policy."""
        self._auth_failure_callback = callback

    @classmethod
    def from_env(cls) -> HttpVault:
        addr = vault_addr()
        if not addr:
            raise VaultTransportError("Vault address is not configured.")
        return cls(
            addr=addr,
            token=vault_token(),
            namespace=vault_namespace(),
            mount=vault_mount_point(),
            approle_mount=vault_approle_mount_point(),
            timeout_seconds=vault_timeout_seconds(),
            verify=vault_verify(),
            role_id=vault_role_id(),
            secret_id=vault_secret_id(),
        )

    def put_document(
        self, path: str, document: dict[str, object], *, cas: int | None = None
    ) -> None:
        payload: dict[str, object] = {"data": document}
        if cas is not None:
            payload["options"] = {"cas": cas}
        self._json("POST", self._kv_data_url(path), payload=payload)

    def get_document(self, path: str) -> dict[str, object] | None:
        payload = self._json("GET", self._kv_data_url(path), missing_ok=True)
        if payload is None:
            return None
        data = payload.get("data") or {}
        inner = data.get("data") if isinstance(data, dict) else None
        return dict(inner) if isinstance(inner, dict) else None

    def get_versioned_document(
        self, path: str
    ) -> tuple[dict[str, object] | None, int | None]:
        payload = self._json("GET", self._kv_data_url(path), missing_ok=True)
        if payload is None:
            return None, None
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return None, None
        document = data.get("data")
        metadata = data.get("metadata")
        version = metadata.get("version") if isinstance(metadata, dict) else None
        return (
            dict(document) if isinstance(document, dict) else None,
            int(version) if version is not None else None,
        )

    def list_names(self, path: str) -> list[str]:
        payload = self._json("LIST", self._kv_meta_url(path), missing_ok=True)
        if payload is None:
            return []
        data = payload.get("data") or {}
        keys = data.get("keys") if isinstance(data, dict) else None
        if not isinstance(keys, list):
            return []
        names = [str(item).rstrip("/") for item in keys if str(item).rstrip("/")]
        return sorted(names)

    def delete_document(self, path: str) -> bool:
        payload = self._json("DELETE", self._kv_meta_url(path), missing_ok=True)
        return payload is not None

    def delete_tree(self, path: str) -> None:
        """Delete every KV v2 document below ``path`` using the current token.

        KV v2 does not support deleting a directory with a tenant-scoped token
        unless it has delete access to the directory metadata itself. Walking
        the tenant's own listable path and deleting leaf metadata keeps cleanup
        within the same tenant policy granted for normal secret operations.
        """
        names = self.list_names(path)
        if not names:
            return
        for name in names:
            child_path = f"{path.strip('/')}/{name}"
            if self.list_names(child_path):
                self.delete_tree(child_path)
            else:
                self.delete_document(child_path)

    def write_policy(self, name: str, policy: str) -> None:
        self._json("PUT", f"{self._addr}/v1/sys/policy/{name}", payload={"policy": policy})

    def read_policy(self, name: str) -> str | None:
        payload = self._json(
            "GET", f"{self._addr}/v1/sys/policy/{name}", missing_ok=True
        )
        if payload is None:
            return None
        data = payload.get("data") or {}
        policy = (
            (data.get("rules") or data.get("policy"))
            if isinstance(data, dict)
            else None
        ) or payload.get("rules") or payload.get("policy")
        return str(policy) if policy is not None else None

    def read_approle(self, role_name: str, *, mount: str) -> dict[str, object] | None:
        return self._json("GET", f"{self._addr}/v1/auth/{mount}/role/{role_name}", missing_ok=True)

    def write_approle(
        self,
        role_name: str,
        *,
        mount: str,
        token_policies: list[str],
        bind_secret_id: bool = True,
        token_no_default_policy: bool = True,
        secret_id_num_uses: int | None = None,
        secret_id_ttl: str | int | None = None,
        token_ttl: str | int | None = None,
        token_max_ttl: str | int | None = None,
        token_period: str | int = 0,
    ) -> None:
        self._json(
            "POST",
            f"{self._addr}/v1/auth/{mount}/role/{role_name}",
            payload={
                "token_policies": token_policies,
                "bind_secret_id": bind_secret_id,
                "token_no_default_policy": token_no_default_policy,
                "secret_id_num_uses": secret_id_num_uses,
                "secret_id_ttl": secret_id_ttl,
                "token_ttl": token_ttl,
                "token_max_ttl": token_max_ttl,
                "token_period": token_period,
            },
        )

    def read_approle_role_id(self, role_name: str, *, mount: str) -> str:
        payload = self._json("GET", f"{self._addr}/v1/auth/{mount}/role/{role_name}/role-id")
        data = (payload or {}).get("data") or {}
        role_id = data.get("role_id") if isinstance(data, dict) else None
        if not role_id:
            raise VaultTransportError("Vault AppRole did not return a role_id.")
        return str(role_id)

    def mint_approle_secret_id(self, role_name: str, *, mount: str) -> AppRoleSecret:
        # The broker creates a throwaway credential only for the immediately
        # following login. One use makes Vault consume both the SecretID and
        # accessor on successful authentication, even if the role permits more.
        payload = self._json(
            "POST",
            f"{self._addr}/v1/auth/{mount}/role/{role_name}/secret-id",
            payload={"num_uses": 1},
        )
        data = (payload or {}).get("data") or {}
        secret_id = data.get("secret_id") if isinstance(data, dict) else None
        if not secret_id:
            raise VaultTransportError("Vault AppRole did not return a secret_id.")
        accessor = data.get("secret_id_accessor") if isinstance(data, dict) else None
        return AppRoleSecret(secret_id=str(secret_id), secret_id_accessor=None if accessor is None else str(accessor))

    def destroy_approle_secret_id(
        self, role_name: str, *, mount: str, secret_id: str
    ) -> None:
        self._json(
            "POST",
            f"{self._addr}/v1/auth/{mount}/role/{role_name}/secret-id/destroy",
            payload={"secret_id": secret_id},
            missing_ok=True,
        )

    def destroy_approle_secret_id_accessor(
        self, role_name: str, *, mount: str, secret_id_accessor: str
    ) -> None:
        self._json(
            "POST",
            f"{self._addr}/v1/auth/{mount}/role/{role_name}/secret-id-accessor/destroy",
            payload={"secret_id_accessor": secret_id_accessor},
            missing_ok=True,
        )

    def login_approle(self, *, role_id: str, secret_id: str, mount: str) -> HttpVault:
        payload = self._json(
            "POST",
            f"{self._addr}/v1/auth/{mount}/login",
            payload={"role_id": role_id, "secret_id": secret_id},
            authenticated=False,
        )
        auth = (payload or {}).get("auth") or {}
        token = auth.get("client_token") if isinstance(auth, dict) else None
        if not token:
            raise VaultTransportError("Vault AppRole login did not return a client token.")
        return HttpVault(
            addr=self._addr,
            token=str(token),
            namespace=self._namespace,
            mount=self._mount,
            approle_mount=self._approle_mount,
            timeout_seconds=self._timeout,
            verify=self._verify,
            token_expires_at=_token_expiry(auth),
            token_lease_duration=_lease_duration(auth),
        )

    def store_for_tenant(
        self, tenant_id: str, *, role_name: str, role_id: str | None = None
    ) -> HttpVault:
        mount = self._approle_mount
        if role_id is None:
            role = self.read_approle(role_name, mount=mount)
            if role is None:
                raise VaultTransportError(f"No AppRole for tenant {tenant_id!r}.")
            role_id = self.read_approle_role_id(role_name, mount=mount)
        minted = self.mint_approle_secret_id(role_name, mount=mount)
        try:
            tenant_store = self.login_approle(
                role_id=role_id, secret_id=minted.secret_id, mount=mount
            )
        except Exception:
            try:
                self._destroy_minted_secret_id(role_name, mount=mount, minted=minted)
            except Exception:
                LOGGER.warning(
                    "Could not clean up the AppRole SecretID after login failed for role %s.",
                    role_name,
                )
            raise
        return tenant_store

    def _destroy_minted_secret_id(
        self, role_name: str, *, mount: str, minted: AppRoleSecret
    ) -> None:
        if minted.secret_id_accessor:
            self.destroy_approle_secret_id_accessor(
                role_name,
                mount=mount,
                secret_id_accessor=minted.secret_id_accessor,
            )
        else:
            self.destroy_approle_secret_id(
                role_name, mount=mount, secret_id=minted.secret_id
            )

    def _ensure_token(self) -> str:
        if self._token and (
            self.token_cache_deadline is None
            or self.token_cache_deadline > time.monotonic()
        ):
            return self._token
        if self._role_id and self._secret_id:
            logged_in = self.login_approle(
                role_id=self._role_id, secret_id=self._secret_id, mount=self._approle_mount
            )
            self._token = logged_in._token
            self._token_expires_at = logged_in._token_expires_at
            self._token_lease_duration = logged_in._token_lease_duration
            return self._token or ""
        raise VaultTransportError("Vault is not authenticated.")

    def _kv_data_url(self, path: str) -> str:
        return f"{self._addr}/v1/{self._mount}/data/{path.strip('/')}"

    def _kv_meta_url(self, path: str) -> str:
        return f"{self._addr}/v1/{self._mount}/metadata/{path.strip('/')}"

    def _json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        missing_ok: bool = False,
        authenticated: bool = True,
        _auth_retry: bool = False,
    ) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        if authenticated:
            headers["X-Vault-Token"] = self._ensure_token()
        if self._namespace:
            headers["X-Vault-Namespace"] = self._namespace
        try:
            response = requests.request(
                method,
                url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
                verify=self._verify,
            )
        except requests.RequestException as exc:
            raise VaultTransportError("Vault request failed.") from exc
        if missing_ok and response.status_code in {404, 204}:
            return None if response.status_code == 404 else {}
        if response.status_code == 404 and missing_ok:
            return None
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            if (
                response.status_code in {401, 403}
                and self._auth_failure_callback is not None
                and not _auth_retry
            ):
                refreshed = self._auth_failure_callback(self)
                if refreshed is not self:
                    self._token = refreshed._token
                    self._token_expires_at = refreshed._token_expires_at
                    self._token_lease_duration = refreshed._token_lease_duration
                    return self._json(
                        method,
                        url,
                        payload=payload,
                        missing_ok=missing_ok,
                        authenticated=authenticated,
                        _auth_retry=True,
                    )
            raise VaultTransportError("Vault request failed.") from exc
        if not response.content:
            return {}
        body = response.json()
        return body if isinstance(body, dict) else {}
