from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable
from urllib.parse import quote

try:
    import hvac
    from hvac import exceptions as hvac_exceptions
except ModuleNotFoundError:  # pragma: no cover - environment-dependent optional dependency
    hvac = None
    hvac_exceptions = None

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - requests is expected but keep tests decoupled
    requests = None


logger = logging.getLogger("m8flow.vault.client")
_SECRET_VALUE_FIELD = "value"


class VaultClientError(RuntimeError):
    """Base error for Vault wrapper failures."""


class VaultConfigurationError(VaultClientError):
    """Raised when Vault settings are incomplete."""


class VaultDependencyError(VaultClientError):
    """Raised when the hvac dependency is unavailable."""


class VaultConnectionError(VaultClientError):
    """Raised when Vault cannot be reached."""


class VaultOperationError(VaultClientError):
    """Raised when a Vault operation fails for a non-connectivity reason."""


@dataclass(frozen=True)
class VaultSettings:
    """Resolved runtime settings for Vault integration."""

    addr: str | None
    token: str | None
    role_id: str | None
    secret_id: str | None
    namespace: str | None
    mount_point: str
    secret_path_prefix: str
    verify: bool | str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "VaultSettings":
        from m8flow_backend.config import (
            vault_addr,
            vault_mount_point,
            vault_namespace,
            vault_role_id,
            vault_secret_id,
            vault_secret_path_prefix,
            vault_timeout_seconds,
            vault_token,
            vault_verify,
        )

        return cls(
            addr=vault_addr(),
            token=vault_token(),
            role_id=vault_role_id(),
            secret_id=vault_secret_id(),
            namespace=vault_namespace(),
            mount_point=vault_mount_point(),
            secret_path_prefix=vault_secret_path_prefix(),
            verify=vault_verify(),
            timeout_seconds=vault_timeout_seconds(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.addr and self.auth_method)

    @property
    def connection_requested(self) -> bool:
        return bool(self.addr or self.token or self.role_id or self.secret_id or self.namespace)

    @property
    def has_token_auth(self) -> bool:
        return bool(self.token)

    @property
    def has_approle_auth(self) -> bool:
        return bool(self.role_id and self.secret_id)

    @property
    def auth_method(self) -> str | None:
        if self.has_token_auth:
            return "token"
        if self.has_approle_auth:
            return "approle"
        return None


def _is_connection_error(exc: Exception) -> bool:
    if requests is not None and isinstance(exc, requests.exceptions.RequestException):
        return True

    return isinstance(exc, (ConnectionError, OSError, TimeoutError))


ClientFactory = Callable[[VaultSettings], Any]


def _default_client_factory(settings: VaultSettings) -> Any:
    if hvac is None:
        raise VaultDependencyError(
            "Vault support is not available because the 'hvac' dependency is not installed."
        )

    client = hvac.Client(
        url=settings.addr,
        namespace=settings.namespace or None,
        verify=settings.verify,
        timeout=settings.timeout_seconds,
    )

    if settings.has_token_auth:
        client.token = settings.token
        return client

    if not settings.has_approle_auth:
        raise VaultConfigurationError(
            "Vault authentication is not configured. "
            "Set M8FLOW_VAULT_TOKEN, or set both M8FLOW_VAULT_ROLE_ID and M8FLOW_VAULT_SECRET_ID."
        )

    try:
        response = client.auth.approle.login(
            role_id=str(settings.role_id),
            secret_id=str(settings.secret_id),
        )
    except Exception as exc:
        if _is_connection_error(exc):
            raise VaultConnectionError(f"Could not authenticate to Vault with AppRole: {exc}") from exc
        raise VaultOperationError(f"Could not authenticate to Vault with AppRole: {exc}") from exc

    token = (((response or {}).get("auth") or {}).get("client_token") or getattr(client, "token", None))
    if not token:
        raise VaultOperationError("Vault AppRole login did not return a client token.")

    client.token = token
    return client


def _read_health_status(client: Any) -> dict[str, Any]:
    return client.sys.read_health_status(
        method="GET",
        standby_ok=True,
        performance_standby_code=200,
    )


def _read_mount_metadata(client: Any, mount_point: str) -> dict[str, Any]:
    normalized_mount = (mount_point or "").strip().strip("/")
    if not normalized_mount:
        raise VaultConfigurationError("Vault mount point must not be empty.")

    adapter = getattr(client, "adapter", None)
    if adapter is None or not hasattr(adapter, "get"):
        raise VaultOperationError("Vault client does not support mount metadata inspection.")

    response = adapter.get(f"/v1/sys/internal/ui/mounts/{quote(normalized_mount, safe='')}")
    if not isinstance(response, dict):
        raise VaultOperationError(
            f"Vault mount '{normalized_mount}' did not return a valid metadata response."
        )

    metadata = response.get("data")
    if not isinstance(metadata, dict):
        raise VaultOperationError(f"Vault mount '{normalized_mount}' is unavailable.")

    return metadata


class VaultClient:
    """Thin wrapper around Vault KV v2 secret operations."""

    def __init__(
        self,
        settings: VaultSettings | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._settings = settings or VaultSettings.from_env()
        self._client_factory = client_factory or _default_client_factory
        self._client: Any | None = None

    @classmethod
    def from_env(cls) -> "VaultClient":
        return cls(settings=VaultSettings.from_env())

    @property
    def settings(self) -> VaultSettings:
        return self._settings

    def store_secret(self, secret_name: str, secret_value: str) -> dict[str, Any]:
        client = self._get_client()
        path = self._secret_path(secret_name)

        try:
            response = client.secrets.kv.v2.create_or_update_secret(
                mount_point=self._settings.mount_point,
                path=path,
                secret={_SECRET_VALUE_FIELD: secret_value},
            )
        except Exception as exc:
            raise self._operation_error("store", secret_name, exc) from exc

        return response or {}

    def retrieve_secret(self, secret_name: str) -> str | None:
        client = self._get_client()
        path = self._secret_path(secret_name)

        try:
            response = client.secrets.kv.v2.read_secret_version(
                mount_point=self._settings.mount_point,
                path=path,
            )
        except Exception as exc:
            if self._is_invalid_path_error(exc):
                return None
            raise self._operation_error("retrieve", secret_name, exc) from exc

        payload = (((response or {}).get("data") or {}).get("data") or {})
        value = payload.get(_SECRET_VALUE_FIELD)
        if value is None:
            return None
        return value if isinstance(value, str) else str(value)

    def delete_secret(self, secret_name: str) -> bool:
        client = self._get_client()
        path = self._secret_path(secret_name)

        try:
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                mount_point=self._settings.mount_point,
                path=path,
            )
        except Exception as exc:
            if self._is_invalid_path_error(exc):
                return False
            raise self._operation_error("delete", secret_name, exc) from exc

        return True

    def check_availability(self) -> bool:
        try:
            client = self._get_client()
            _read_health_status(client)
            is_authenticated = getattr(client, "is_authenticated", None)
            if callable(is_authenticated):
                return bool(is_authenticated())
            return True
        except (VaultConfigurationError, VaultDependencyError) as exc:
            logger.info("vault_client: availability check skipped: %s", exc)
            return False
        except Exception as exc:
            logger.warning("vault_client: availability check failed: %s", exc)
            return False

    def assert_startup_ready(self) -> None:
        client = self._get_client()

        try:
            health = _read_health_status(client)
        except Exception as exc:
            raise self._operation_error("validate startup for", "vault", exc) from exc

        if isinstance(health, dict):
            if health.get("initialized") is False:
                raise VaultOperationError("Vault is not initialized.")
            if health.get("sealed") is True:
                raise VaultOperationError("Vault is sealed.")

        is_authenticated = getattr(client, "is_authenticated", None)
        if callable(is_authenticated) and not is_authenticated():
            raise VaultOperationError("Vault authentication failed.")

        try:
            mount_metadata = _read_mount_metadata(client, self._settings.mount_point)
        except VaultClientError:
            raise
        except Exception as exc:
            raise self._operation_error("validate mount access for", "vault", exc) from exc

        options = mount_metadata.get("options") or {}
        if str(options.get("version")) != "2":
            raise VaultOperationError(
                f"Vault mount '{self._settings.mount_point}' is not configured as KV v2."
            )

    def _get_client(self) -> Any:
        if not self._settings.is_configured:
            raise VaultConfigurationError(
                "Vault is not configured. Set M8FLOW_VAULT_ADDR and either "
                "M8FLOW_VAULT_TOKEN or both M8FLOW_VAULT_ROLE_ID and M8FLOW_VAULT_SECRET_ID."
            )

        if self._client is None:
            self._client = self._client_factory(self._settings)

        return self._client

    def _secret_path(self, secret_name: str) -> str:
        normalized_secret_name = (secret_name or "").strip().strip("/")
        if not normalized_secret_name:
            raise ValueError("secret_name must not be empty.")

        prefix = self._settings.secret_path_prefix.strip().strip("/")
        if prefix:
            if normalized_secret_name == prefix or normalized_secret_name.startswith(f"{prefix}/"):
                return normalized_secret_name
            return f"{prefix}/{normalized_secret_name}"
        return normalized_secret_name

    def _operation_error(self, action: str, secret_name: str, exc: Exception) -> VaultClientError:
        if self._is_connection_error(exc):
            return VaultConnectionError(
                f"Could not {action} secret '{secret_name}' because Vault is unreachable: {exc}"
            )

        return VaultOperationError(f"Could not {action} secret '{secret_name}' in Vault: {exc}")

    @staticmethod
    def _is_invalid_path_error(exc: Exception) -> bool:
        invalid_path_type = getattr(hvac_exceptions, "InvalidPath", None) if hvac_exceptions else None
        return bool(invalid_path_type and isinstance(exc, invalid_path_type))

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        return _is_connection_error(exc)


def get_vault_client() -> VaultClient:
    """Return a Vault client wrapper using the current environment-based settings."""
    return VaultClient.from_env()
