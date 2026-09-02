from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Mapping
from urllib.parse import quote

from flask import has_app_context

from m8flow_backend.services.audit_log_service import get_audit_log_service

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

    def with_approle_credentials(self, *, role_id: str, secret_id: str) -> "VaultSettings":
        normalized_role_id = str(role_id or "").strip()
        normalized_secret_id = str(secret_id or "").strip()
        if not normalized_role_id:
            raise ValueError("role_id must not be empty.")
        if not normalized_secret_id:
            raise ValueError("secret_id must not be empty.")

        return VaultSettings(
            addr=self.addr,
            token=None,
            role_id=normalized_role_id,
            secret_id=normalized_secret_id,
            namespace=self.namespace,
            mount_point=self.mount_point,
            secret_path_prefix=self.secret_path_prefix,
            verify=self.verify,
            timeout_seconds=self.timeout_seconds,
        )


@dataclass(frozen=True)
class VaultAppRoleSecretId:
    """Generated AppRole secret ID payload returned by Vault."""

    secret_id: str
    secret_id_accessor: str | None = None


@dataclass(frozen=True)
class VaultAppRole:
    """AppRole configuration as returned by Vault."""

    data: dict[str, Any]


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


def _is_mount_metadata_forbidden_error(exc: Exception) -> bool:
    forbidden_type = getattr(hvac_exceptions, "Forbidden", None) if hvac_exceptions else None
    if forbidden_type and isinstance(exc, forbidden_type):
        return True

    message = str(exc).lower()
    return "sys/internal/ui/mounts" in message and "403" in message


class VaultClient:
    """Thin wrapper around Vault KV v2 secret operations."""

    def __init__(
        self,
        settings: VaultSettings | None = None,
        client_factory: ClientFactory | None = None,
        audit_log_service=None,
    ) -> None:
        self._settings = settings or VaultSettings.from_env()
        self._client_factory = client_factory or _default_client_factory
        self._client: Any | None = None
        self._audit_log_service = audit_log_service or get_audit_log_service()

    @classmethod
    def from_env(cls) -> "VaultClient":
        return cls(settings=VaultSettings.from_env())

    @property
    def settings(self) -> VaultSettings:
        return self._settings

    def store_secret(self, secret_name: str, secret_value: str) -> dict[str, Any]:
        return self.store_secret_document(secret_name, {_SECRET_VALUE_FIELD: secret_value})

    def create_or_update_policy(self, policy_name: str, policy: str) -> None:
        client = self._get_client()
        normalized_policy_name = self._require_non_empty(policy_name, "policy_name")
        normalized_policy = self._require_non_empty(policy, "policy")

        try:
            client.sys.create_or_update_policy(
                name=normalized_policy_name,
                policy=normalized_policy,
            )
        except Exception as exc:
            raise self._resource_error("create or update", "policy", normalized_policy_name, exc) from exc

    def create_or_update_approle(
        self,
        role_name: str,
        *,
        token_policies: list[str],
        mount_point: str = "approle",
        token_no_default_policy: bool = True,
        secret_id_num_uses: int | None = None,
        secret_id_ttl: str | int | None = None,
        token_ttl: str | int | None = None,
        token_max_ttl: str | int | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        normalized_role_name = self._require_non_empty(role_name, "role_name")
        normalized_mount_point = self._require_non_empty(mount_point, "mount_point")
        normalized_policies = [policy.strip() for policy in token_policies if isinstance(policy, str) and policy.strip()]
        if not normalized_policies:
            raise ValueError("token_policies must contain at least one non-empty policy name.")

        approle_payload: dict[str, Any] = {
            "role_name": normalized_role_name,
            "mount_point": normalized_mount_point,
            "token_policies": normalized_policies,
            "bind_secret_id": True,
            "token_no_default_policy": token_no_default_policy,
        }
        if secret_id_num_uses is not None:
            approle_payload["secret_id_num_uses"] = secret_id_num_uses
        if secret_id_ttl is not None:
            approle_payload["secret_id_ttl"] = secret_id_ttl
        if token_ttl is not None:
            approle_payload["token_ttl"] = token_ttl
        if token_max_ttl is not None:
            approle_payload["token_max_ttl"] = token_max_ttl

        try:
            response = client.auth.approle.create_or_update_approle(**approle_payload)
        except Exception as exc:
            raise self._resource_error("create or update", "AppRole", normalized_role_name, exc) from exc

        return response or {}

    def read_approle(
        self,
        role_name: str,
        *,
        mount_point: str = "approle",
    ) -> VaultAppRole | None:
        client = self._get_client()
        normalized_role_name = self._require_non_empty(role_name, "role_name")
        normalized_mount_point = self._require_non_empty(mount_point, "mount_point")

        try:
            response = client.auth.approle.read_role(
                role_name=normalized_role_name,
                mount_point=normalized_mount_point,
            )
        except Exception as exc:
            if self._is_invalid_path_error(exc):
                return None
            raise self._resource_error("read", "AppRole", normalized_role_name, exc) from exc

        payload = (response or {}).get("data") or {}
        if not isinstance(payload, dict) or not payload:
            return None

        return VaultAppRole(data=dict(payload))

    def read_approle_role_id(self, role_name: str, *, mount_point: str = "approle") -> str:
        client = self._get_client()
        normalized_role_name = self._require_non_empty(role_name, "role_name")
        normalized_mount_point = self._require_non_empty(mount_point, "mount_point")

        try:
            response = client.auth.approle.read_role_id(
                role_name=normalized_role_name,
                mount_point=normalized_mount_point,
            )
        except Exception as exc:
            raise self._resource_error("read", "AppRole role ID for", normalized_role_name, exc) from exc

        role_id = (((response or {}).get("data") or {}).get("role_id") or "").strip()
        if not role_id:
            raise VaultOperationError(
                f"Vault AppRole '{normalized_role_name}' did not return a role_id."
            )
        return role_id

    def generate_approle_secret_id(
        self,
        role_name: str,
        *,
        mount_point: str = "approle",
    ) -> VaultAppRoleSecretId:
        client = self._get_client()
        normalized_role_name = self._require_non_empty(role_name, "role_name")
        normalized_mount_point = self._require_non_empty(mount_point, "mount_point")

        try:
            response = client.auth.approle.generate_secret_id(
                role_name=normalized_role_name,
                mount_point=normalized_mount_point,
            )
        except Exception as exc:
            raise self._resource_error("generate", "AppRole secret ID for", normalized_role_name, exc) from exc

        payload = (response or {}).get("data") or {}
        secret_id = str(payload.get("secret_id") or "").strip()
        if not secret_id:
            raise VaultOperationError(
                f"Vault AppRole '{normalized_role_name}' did not return a secret_id."
            )

        secret_id_accessor_raw = payload.get("secret_id_accessor")
        secret_id_accessor = (
            str(secret_id_accessor_raw).strip() if secret_id_accessor_raw is not None else None
        ) or None
        return VaultAppRoleSecretId(
            secret_id=secret_id,
            secret_id_accessor=secret_id_accessor,
        )

    def store_secret_document(
        self,
        secret_name: str,
        secret_data: Mapping[str, Any],
        expected_version: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        path = self._secret_path(secret_name)

        request: dict[str, Any] = {
            "mount_point": self._settings.mount_point,
            "path": path,
            "secret": dict(secret_data),
        }
        if expected_version is not None:
            try:
                request["cas"] = int(expected_version)
            except (TypeError, ValueError) as exc:
                raise ValueError("expected_version must be an integer string.") from exc

        try:
            response = client.secrets.kv.v2.create_or_update_secret(**request)
        except Exception as exc:
            raise self._operation_error("store", secret_name, exc) from exc

        return response or {}

    def retrieve_secret(self, secret_name: str) -> str | None:
        payload = self.retrieve_secret_document(secret_name)
        if payload is None:
            return None

        value = payload.get(_SECRET_VALUE_FIELD)
        if value is None:
            return None
        return value if isinstance(value, str) else str(value)

    def retrieve_secret_document(self, secret_name: str) -> dict[str, Any] | None:
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
        if not isinstance(payload, dict) or not payload:
            return None
        return dict(payload)

    def list_secret_names(self, secret_name_prefix: str) -> list[str]:
        client = self._get_client()
        path = self._secret_path(secret_name_prefix)

        try:
            response = client.secrets.kv.v2.list_secrets(
                mount_point=self._settings.mount_point,
                path=path,
            )
        except Exception as exc:
            if self._is_invalid_path_error(exc):
                return []
            raise self._operation_error("list", secret_name_prefix, exc) from exc

        payload = ((response or {}).get("data") or {}).get("keys") or []
        if not isinstance(payload, list):
            return []
        return [entry for entry in payload if isinstance(entry, str)]

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

    def check_availability(self, *, audit: bool = True, transitions_only: bool = False) -> bool:
        try:
            client = self._get_client()
            _read_health_status(client)
            is_authenticated = getattr(client, "is_authenticated", None)
            authenticated = True
            if callable(is_authenticated):
                authenticated = bool(is_authenticated())
            available = authenticated
            if audit:
                self._audit_availability_check(
                    status="success" if available else "failed",
                    severity="info" if available else "warning",
                    message=(
                        "Vault availability check succeeded."
                        if available
                        else "Vault availability check failed."
                    ),
                    details={
                        "configured": self._settings.is_configured,
                        "authenticated": authenticated,
                        "mount_point": self._settings.mount_point,
                        "auth_method": self._settings.auth_method,
                    },
                    transitions_only=transitions_only,
                )
            return available
        except (VaultConfigurationError, VaultDependencyError) as exc:
            logger.info("vault_client: availability check skipped error_type=%s", type(exc).__name__)
            if audit:
                self._audit_availability_check(
                    status="skipped",
                    severity="warning",
                    message="Vault availability check skipped.",
                    details={
                        "configured": self._settings.is_configured,
                        "mount_point": self._settings.mount_point,
                        "auth_method": self._settings.auth_method,
                        "error_type": type(exc).__name__,
                    },
                    transitions_only=transitions_only,
                )
            return False
        except Exception as exc:
            logger.warning("vault_client: availability check failed error_type=%s", type(exc).__name__)
            if audit:
                self._audit_availability_check(
                    status="failed",
                    severity="error",
                    message="Vault availability check failed.",
                    details={
                        "configured": self._settings.is_configured,
                        "mount_point": self._settings.mount_point,
                        "auth_method": self._settings.auth_method,
                        "error_type": type(exc).__name__,
                    },
                    transitions_only=transitions_only,
                )
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
        except VaultClientError as exc:
            if _is_mount_metadata_forbidden_error(exc):
                logger.info(
                    "vault_client: skipping mount metadata validation for mount '%s' because "
                    "the configured Vault identity is intentionally least-privilege: %s",
                    self._settings.mount_point,
                    exc,
                )
                return
            raise
        except Exception as exc:
            if _is_mount_metadata_forbidden_error(exc):
                logger.info(
                    "vault_client: skipping mount metadata validation for mount '%s' because "
                    "the configured Vault identity is intentionally least-privilege: %s",
                    self._settings.mount_point,
                    exc,
                )
                return
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
        return self._resource_error(action, "secret", secret_name, exc)

    def _audit_availability_check(
        self,
        *,
        status: str,
        severity: str,
        message: str,
        details: dict[str, Any],
        transitions_only: bool = False,
    ) -> None:
        if not has_app_context():
            return

        if transitions_only and not self._should_record_availability_audit_transition(status):
            return

        self._audit_log_service.try_record_event(
            category="vault",
            event_type="vault.health.check",
            source="vault_client",
            status=status,
            severity=severity,
            message=message,
            details=details,
        )

    def _should_record_availability_audit_transition(self, status: str) -> bool:
        latest_event = self._audit_log_service.try_latest_event(
            category="vault",
            event_type="vault.health.check",
            source="vault_client",
        )
        if latest_event is None:
            return True

        latest_status = str(getattr(latest_event, "status", "") or "").strip()
        return latest_status != status

    def _resource_error(
        self,
        action: str,
        resource_type: str,
        resource_name: str,
        exc: Exception,
    ) -> VaultClientError:
        if self._is_connection_error(exc):
            return VaultConnectionError(
                f"Could not {action} {resource_type} '{resource_name}' because Vault is unreachable: {exc}"
            )

        return VaultOperationError(
            f"Could not {action} {resource_type} '{resource_name}' in Vault: {exc}"
        )

    @staticmethod
    def _require_non_empty(value: str, field_name: str) -> str:
        normalized_value = (value or "").strip()
        if not normalized_value:
            raise ValueError(f"{field_name} must not be empty.")
        return normalized_value

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
