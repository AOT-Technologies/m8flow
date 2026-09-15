"""HashiCorp Vault KV v2 + AppRole HTTP adapter.

Talks to Vault over ``requests``. Tests inject in-memory stores instead of this
adapter, so the provider never needs a live Vault process.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class AppRoleSecret:
    secret_id: str
    secret_id_accessor: str | None = None


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

    def put_document(self, path: str, document: dict[str, object]) -> None:
        self._json("POST", self._kv_data_url(path), payload={"data": document})

    def get_document(self, path: str) -> dict[str, object] | None:
        payload = self._json("GET", self._kv_data_url(path), missing_ok=True)
        if payload is None:
            return None
        data = payload.get("data") or {}
        inner = data.get("data") if isinstance(data, dict) else None
        return dict(inner) if isinstance(inner, dict) else None

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

    def write_policy(self, name: str, policy: str) -> None:
        self._json("PUT", f"{self._addr}/v1/sys/policy/{name}", payload={"policy": policy})

    def read_approle(self, role_name: str, *, mount: str) -> dict[str, object] | None:
        return self._json("GET", f"{self._addr}/v1/auth/{mount}/role/{role_name}", missing_ok=True)

    def write_approle(
        self,
        role_name: str,
        *,
        mount: str,
        token_policies: list[str],
        token_no_default_policy: bool = True,
        secret_id_num_uses: int | None = None,
        secret_id_ttl: str | int | None = None,
        token_ttl: str | int | None = None,
        token_max_ttl: str | int | None = None,
    ) -> None:
        self._json(
            "POST",
            f"{self._addr}/v1/auth/{mount}/role/{role_name}",
            payload={
                "token_policies": token_policies,
                "token_no_default_policy": token_no_default_policy,
                "secret_id_num_uses": secret_id_num_uses,
                "secret_id_ttl": secret_id_ttl,
                "token_ttl": token_ttl,
                "token_max_ttl": token_max_ttl,
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
        payload = self._json("POST", f"{self._addr}/v1/auth/{mount}/role/{role_name}/secret-id")
        data = (payload or {}).get("data") or {}
        secret_id = data.get("secret_id") if isinstance(data, dict) else None
        if not secret_id:
            raise VaultTransportError("Vault AppRole did not return a secret_id.")
        accessor = data.get("secret_id_accessor") if isinstance(data, dict) else None
        return AppRoleSecret(secret_id=str(secret_id), secret_id_accessor=None if accessor is None else str(accessor))

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
        )

    def store_for_tenant(self, tenant_id: str, *, role_name: str) -> HttpVault:
        mount = self._approle_mount
        role = self.read_approle(role_name, mount=mount)
        if role is None:
            raise VaultTransportError(f"No AppRole for tenant {tenant_id!r}.")
        role_id = self.read_approle_role_id(role_name, mount=mount)
        minted = self.mint_approle_secret_id(role_name, mount=mount)
        return self.login_approle(role_id=role_id, secret_id=minted.secret_id, mount=mount)

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        if self._role_id and self._secret_id:
            logged_in = self.login_approle(
                role_id=self._role_id, secret_id=self._secret_id, mount=self._approle_mount
            )
            self._token = logged_in._token
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
            raise VaultTransportError("Vault request failed.") from exc
        if not response.content:
            return {}
        body = response.json()
        return body if isinstance(body, dict) else {}
