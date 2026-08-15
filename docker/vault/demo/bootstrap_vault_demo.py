#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import sys
import time
import hashlib
import re
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from cryptography.fernet import Fernet, InvalidToken

from demo_identity import ensure_backend_src_on_path, wait_for_demo_tenant_identity
from seeded_secrets import SeededSecretSpec, default_seeded_secret_spec, load_seeded_secret_specs


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


VAULT_ADDR = (os.getenv("M8FLOW_VAULT_INTERNAL_ADDR") or "http://vault:8200").rstrip("/")
MOUNT_POINT = (os.getenv("M8FLOW_VAULT_MOUNT_POINT") or "kv").strip().strip("/")
PATH_PREFIX = (os.getenv("M8FLOW_VAULT_SECRET_PATH_PREFIX") or "m8flow").strip().strip("/")
APPROLE_MOUNT_POINT = (os.getenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT") or "approle").strip().strip("/")
TENANT_POLICY_PREFIX = (os.getenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX") or "m8flow-tenant-policy").strip()
TENANT_ROLE_PREFIX = (os.getenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX") or "m8flow-tenant-role").strip()
BROKER_POLICY_NAME = (os.getenv("M8FLOW_VAULT_POLICY_NAME") or "m8flow").strip()
BROKER_APPROLE_NAME = (os.getenv("M8FLOW_VAULT_APPROLE_NAME") or "m8flow").strip()
DEMO_OVERWRITE = _truthy(os.getenv("M8FLOW_VAULT_DEMO_OVERWRITE"))
WAIT_TIMEOUT_SECONDS = float(os.getenv("M8FLOW_VAULT_DEMO_WAIT_TIMEOUT_SECONDS") or "180")
WAIT_INTERVAL_SECONDS = float(os.getenv("M8FLOW_VAULT_DEMO_WAIT_INTERVAL_SECONDS") or "2")
VAULT_REQUEST_TIMEOUT_SECONDS = float(os.getenv("M8FLOW_VAULT_DEMO_HTTP_TIMEOUT_SECONDS") or "10")
INIT_REQUEST_TIMEOUT_SECONDS = float(
    os.getenv("M8FLOW_VAULT_DEMO_INIT_TIMEOUT_SECONDS") or str(max(VAULT_REQUEST_TIMEOUT_SECONDS, 30.0))
)
STATE_DIR = Path(os.getenv("M8FLOW_VAULT_DEMO_STATE_DIR") or "/vault/demo")
INIT_FILE = STATE_DIR / "init.json"
ROLE_ID_FILE = STATE_DIR / "m8flow-role-id"
SECRET_ID_FILE = STATE_DIR / "m8flow-secret-id"
RUNTIME_ENV_FILE = STATE_DIR / "runtime.env"
VERIFICATION_FILE = STATE_DIR / "verification.json"
SECRETS_FILE = Path(os.getenv("M8FLOW_VAULT_DEMO_SECRETS_FILE") or "/app/docker/vault/demo/secrets.yml")
SECRETS_SAMPLE_FILE = Path("/app/docker/vault/demo/secrets.yml.sample")
POLICY_TEMPLATE = Path(
    os.getenv("M8FLOW_VAULT_POLICY_TEMPLATE") or "/app/docker/vault/policies/m8flow-policy.hcl.tpl"
)
HEALTH_PATH = "sys/health?standbyok=true&perfstandbyok=true"
LEADER_PATH = "sys/leader"
_ENCRYPTED_STATE_PREFIX = "m8flow-vault-demo:enc:v1:"


def fail(message: str) -> None:
    raise RuntimeError(message)


def _redact_sensitive_exception_message(message: str) -> str:
    sanitized = " ".join(message.split())
    sanitized = re.sub(
        r"((?:secret_id|role_id|root_token|client_token|access_token|refresh_token|token|value)\s*=\s*)([^,\s]+)",
        r"\1[redacted]",
        sanitized,
        flags=re.I,
    )
    sanitized = re.sub(
        r'("(?:secret_id|role_id|root_token|client_token|access_token|refresh_token|token|value)"\s*:\s*")([^"]+)(")',
        r"\1[redacted]\3",
        sanitized,
        flags=re.I,
    )
    return sanitized


def format_bootstrap_failure_message(exc: Exception) -> str:
    message = _redact_sensitive_exception_message(str(exc))
    if message:
        return f"{type(exc).__name__}: {message}"
    return type(exc).__name__


def _set_file_mode(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _state_cipher() -> Fernet:
    state_key = (
        os.getenv("M8FLOW_VAULT_DEMO_STATE_KEY")
        or os.getenv("M8FLOW_BACKEND_ENCRYPTION_KEY")
        or os.getenv("FLASK_SESSION_SECRET_KEY")
    )
    if not isinstance(state_key, str) or not state_key.strip():
        fail(
            "Vault demo state encryption key is missing. "
            "Set M8FLOW_VAULT_DEMO_STATE_KEY or M8FLOW_BACKEND_ENCRYPTION_KEY."
        )

    digest = hashlib.sha256(state_key.strip().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def write_plain_text_file(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _set_file_mode(path, mode)


def write_plain_json_file(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    write_plain_text_file(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", mode=mode)


def write_encrypted_text_file(path: Path, text: str, mode: int = 0o600) -> None:
    ciphertext = _state_cipher().encrypt(text.encode("utf-8")).decode("utf-8")
    write_plain_text_file(path, _ENCRYPTED_STATE_PREFIX + ciphertext + "\n", mode=mode)


def write_encrypted_json_file(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    write_encrypted_text_file(path, json.dumps(payload, indent=2, sort_keys=True), mode=mode)


def read_encrypted_text_file(path: Path) -> str:
    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return raw_text
    if not raw_text.startswith(_ENCRYPTED_STATE_PREFIX):
        return raw_text

    ciphertext = raw_text[len(_ENCRYPTED_STATE_PREFIX) :]
    try:
        plaintext = _state_cipher().decrypt(ciphertext.encode("utf-8"))
    except InvalidToken as exc:
        raise RuntimeError(f"Vault demo state file could not be decrypted: {path}") from exc
    return plaintext.decode("utf-8")


def load_encrypted_json_file(path: Path) -> dict[str, Any]:
    return json.loads(read_encrypted_text_file(path))


def format_missing_secrets_file_message(path: Path) -> str:
    message = f"Vault demo secrets file is missing: {path}"
    if path.name == "secrets.yml":
        message += (
            f". Copy {SECRETS_SAMPLE_FILE} to {path} and edit the local values you want "
            "seeded for the m8flow tenant."
        )
    return message


def log_missing_secrets_file_notice(_message: str) -> None:
    print(
        "vault-demo: Vault demo secrets file is missing. Proceeding with the demo bootstrap marker secret.",
        flush=True,
    )


def seeded_secret_logical_path(secret: SeededSecretSpec) -> str:
    return f"{PATH_PREFIX}/tenants/{secret.tenant_id}/secrets/{secret.secret_name}"


def remove_generated_files() -> None:
    for path in (ROLE_ID_FILE, SECRET_ID_FILE, RUNTIME_ENV_FILE, VERIFICATION_FILE):
        path.unlink(missing_ok=True)


def vault_request(
    method: str,
    api_path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
    timeout_seconds: float = VAULT_REQUEST_TIMEOUT_SECONDS,
) -> tuple[int, dict[str, Any] | None, str]:
    url = f"{VAULT_ADDR}/v1/{api_path.lstrip('/')}"
    headers: dict[str, str] = {}
    data: bytes | None = None
    if token:
        headers["X-Vault-Token"] = token
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    response_status: int
    response_body: str
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_status = int(response.getcode())
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        response_status = int(exc.code)
        response_body = exc.read().decode("utf-8")
    except TimeoutError as exc:
        del exc
        fail(f"Vault API {method} /v1/{api_path.lstrip('/')} timed out after {timeout_seconds:g}s.")
    except error.URLError as exc:
        del exc
        fail(f"Could not reach Vault at {VAULT_ADDR}.")

    parsed: dict[str, Any] | None = None
    if response_body.strip():
        try:
            loaded = json.loads(response_body)
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError:
            parsed = None

    if response_status not in expected_statuses:
        fail(
            f"Vault API {method} /v1/{api_path.lstrip('/')} returned {response_status}. "
            "Response body suppressed to avoid logging sensitive data."
        )

    return response_status, parsed, response_body


def wait_for_vault_status() -> dict[str, Any]:
    deadline = time.time() + WAIT_TIMEOUT_SECONDS
    last_error: str | None = None

    while time.time() < deadline:
        try:
            _status_code, payload, _body = vault_request(
                "GET",
                HEALTH_PATH,
                expected_statuses=(200, 429, 472, 473, 501, 503),
            )
            if isinstance(payload, dict):
                return payload
            last_error = "health endpoint returned a non-JSON response"
        except RuntimeError:
            last_error = "health request failed"
        time.sleep(WAIT_INTERVAL_SECONDS)

    if last_error == "health endpoint returned a non-JSON response":
        fail(f"Timed out waiting for Vault health at {VAULT_ADDR}. The health endpoint returned a non-JSON response.")
    fail(f"Timed out waiting for Vault health at {VAULT_ADDR}.")


def wait_for_active_node() -> dict[str, Any]:
    deadline = time.time() + WAIT_TIMEOUT_SECONDS
    last_error: str | None = None

    while time.time() < deadline:
        try:
            _status_code, payload, body = vault_request(
                "GET",
                LEADER_PATH,
                expected_statuses=(200, 500),
            )
            if isinstance(payload, dict):
                if payload.get("ha_enabled") is False:
                    return payload
                if payload.get("is_self") is True:
                    return payload
                last_error = "leader not active yet"
            elif "active cluster node not found" in body:
                last_error = "active cluster node not found"
            else:
                last_error = "leader endpoint returned a non-JSON response"
        except RuntimeError:
            last_error = "leader request failed"
        time.sleep(WAIT_INTERVAL_SECONDS)

    if last_error == "leader endpoint returned a non-JSON response":
        fail(
            f"Timed out waiting for the local Vault node to become active at {VAULT_ADDR}. "
            "The leader endpoint returned a non-JSON response."
        )
    fail(f"Timed out waiting for the local Vault node to become active at {VAULT_ADDR}.")


def load_init_payload() -> dict[str, Any]:
    if not INIT_FILE.exists():
        fail(
            "Vault is already initialized, but the persisted demo init file is missing. "
            "Reset both the Vault data volume and the vault-demo state volume, then retry."
        )
    return load_encrypted_json_file(INIT_FILE)


def root_token_from_init(payload: dict[str, Any]) -> str:
    root_token = payload.get("root_token")
    if not isinstance(root_token, str) or not root_token.strip():
        fail("Persisted dev init payload does not contain a usable root token.")
    return root_token.strip()


def unseal_key_from_init(payload: dict[str, Any]) -> str:
    keys = payload.get("keys_base64") or payload.get("unseal_keys_b64") or []
    if not isinstance(keys, list) or not keys:
        fail("Persisted dev init payload does not contain any unseal keys.")
    first_key = keys[0]
    if not isinstance(first_key, str) or not first_key.strip():
        fail("Persisted dev init payload contains an empty unseal key.")
    return first_key.strip()


def initialize_if_needed(status: dict[str, Any]) -> dict[str, Any]:
    if status.get("initialized") is not False:
        return status

    print("vault-demo: Vault is uninitialized. Initializing a development-only instance.", flush=True)
    remove_generated_files()
    _status_code, payload, _body = vault_request(
        "PUT",
        "sys/init",
        payload={"secret_shares": 1, "secret_threshold": 1},
        expected_statuses=(200,),
        timeout_seconds=INIT_REQUEST_TIMEOUT_SECONDS,
    )
    if not isinstance(payload, dict):
        fail("Vault init did not return a JSON payload.")
    write_encrypted_json_file(INIT_FILE, payload)
    return wait_for_vault_status()


def unseal_if_needed(status: dict[str, Any]) -> dict[str, Any]:
    if status.get("sealed") is not True:
        return status

    init_payload = load_init_payload()
    print("vault-demo: Vault is sealed. Unsealing with the persisted development key.", flush=True)
    _status_code, payload, _body = vault_request(
        "PUT",
        "sys/unseal",
        payload={"key": unseal_key_from_init(init_payload)},
        expected_statuses=(200,),
    )
    if isinstance(payload, dict) and payload.get("sealed") is True:
        fail("Vault remained sealed after submitting the persisted development unseal key.")
    return wait_for_vault_status()


def ensure_kv_v2_mount(root_token: str) -> None:
    _status_code, payload, _body = vault_request("GET", "sys/mounts", token=root_token, expected_statuses=(200,))
    mounts = payload or {}
    mount_key = f"{MOUNT_POINT}/"
    mount_entry = mounts.get(mount_key)
    if mount_entry is None:
        print(f"vault-demo: Enabling KV v2 mount '{MOUNT_POINT}'.", flush=True)
        vault_request(
            "POST",
            f"sys/mounts/{parse.quote(MOUNT_POINT, safe='')}",
            token=root_token,
            payload={"type": "kv", "options": {"version": "2"}},
            expected_statuses=(200, 204),
        )
        return

    if not isinstance(mount_entry, dict) or mount_entry.get("type") != "kv":
        fail(f"Vault mount '{MOUNT_POINT}' already exists but is not a KV secrets engine.")

    options = mount_entry.get("options") or {}
    if str(options.get("version")) != "2":
        fail(f"Vault mount '{MOUNT_POINT}' already exists but is not configured as KV v2.")


def ensure_approle_auth(root_token: str) -> None:
    _status_code, payload, _body = vault_request("GET", "sys/auth", token=root_token, expected_statuses=(200,))
    auth_methods = payload or {}
    mount_key = f"{APPROLE_MOUNT_POINT}/"
    if mount_key in auth_methods:
        return

    print(f"vault-demo: Enabling the AppRole auth method at mount '{APPROLE_MOUNT_POINT}'.", flush=True)
    vault_request(
        "POST",
        f"sys/auth/{parse.quote(APPROLE_MOUNT_POINT, safe='')}",
        token=root_token,
        payload={"type": "approle"},
        expected_statuses=(200, 204),
    )


def render_policy() -> str:
    if not POLICY_TEMPLATE.exists():
        fail(f"Vault policy template is missing: {POLICY_TEMPLATE}")

    template = POLICY_TEMPLATE.read_text(encoding="utf-8")
    return (
        template.replace("__APPROLE_MOUNT_POINT__", APPROLE_MOUNT_POINT)
        .replace("__TENANT_POLICY_PREFIX__", TENANT_POLICY_PREFIX)
        .replace("__TENANT_ROLE_PREFIX__", TENANT_ROLE_PREFIX)
    )


def ensure_policy(root_token: str) -> None:
    vault_request(
        "PUT",
        f"sys/policies/acl/{parse.quote(BROKER_POLICY_NAME, safe='')}",
        token=root_token,
        payload={"policy": render_policy()},
        expected_statuses=(200, 204),
    )


def ensure_approle_role(root_token: str) -> None:
    print(
        f"vault-demo: Creating or updating broker AppRole '{BROKER_APPROLE_NAME}' with policy '{BROKER_POLICY_NAME}'.",
        flush=True,
    )
    vault_request(
        "POST",
        f"auth/{parse.quote(APPROLE_MOUNT_POINT, safe='')}/role/{parse.quote(BROKER_APPROLE_NAME, safe='')}",
        token=root_token,
        payload={
            "bind_secret_id": True,
            "secret_id_num_uses": 0,
            "secret_id_ttl": 0,
            "token_num_uses": 0,
            "token_policies": [BROKER_POLICY_NAME],
            "token_ttl": "24h",
            "token_max_ttl": "720h",
        },
        expected_statuses=(200, 204),
    )


def read_role_id(root_token: str) -> str:
    _status_code, payload, _body = vault_request(
        "GET",
        f"auth/{parse.quote(APPROLE_MOUNT_POINT, safe='')}/role/{parse.quote(BROKER_APPROLE_NAME, safe='')}/role-id",
        token=root_token,
        expected_statuses=(200,),
    )
    role_id = ((payload or {}).get("data") or {}).get("role_id")
    if not isinstance(role_id, str) or not role_id.strip():
        fail(f"Vault broker AppRole '{BROKER_APPROLE_NAME}' did not return a usable role_id.")
    return role_id.strip()


def approle_login(role_id: str, secret_id: str) -> str:
    _status_code, payload, _body = vault_request(
        "POST",
        f"auth/{parse.quote(APPROLE_MOUNT_POINT, safe='')}/login",
        payload={"role_id": role_id, "secret_id": secret_id},
        expected_statuses=(200,),
    )
    client_token = ((payload or {}).get("auth") or {}).get("client_token")
    if not isinstance(client_token, str) or not client_token.strip():
        fail("Vault AppRole login succeeded but did not return a client token.")
    return client_token.strip()


def generate_secret_id(root_token: str) -> str:
    _status_code, payload, _body = vault_request(
        "POST",
        f"auth/{parse.quote(APPROLE_MOUNT_POINT, safe='')}/role/{parse.quote(BROKER_APPROLE_NAME, safe='')}/secret-id",
        token=root_token,
        payload={},
        expected_statuses=(200,),
    )
    secret_id = ((payload or {}).get("data") or {}).get("secret_id")
    if not isinstance(secret_id, str) or not secret_id.strip():
        fail(f"Vault broker AppRole '{BROKER_APPROLE_NAME}' did not return a usable secret_id.")
    return secret_id.strip()


def ensure_secret_id(root_token: str, role_id: str) -> str:
    if SECRET_ID_FILE.exists():
        existing_secret_id = read_encrypted_text_file(SECRET_ID_FILE).strip()
        if existing_secret_id:
            try:
                approle_login(role_id, existing_secret_id)
                print("vault-demo: Reusing the persisted broker AppRole credential.", flush=True)
                return existing_secret_id
            except RuntimeError:
                print("vault-demo: Persisted broker AppRole credential is invalid; generating a fresh one.", flush=True)

    print("vault-demo: Generating a persisted broker AppRole credential for development use.", flush=True)
    return generate_secret_id(root_token)


def write_runtime_files(role_id: str, secret_id: str) -> None:
    write_encrypted_text_file(ROLE_ID_FILE, role_id + "\n")
    write_encrypted_text_file(SECRET_ID_FILE, secret_id + "\n")
    write_plain_text_file(
        RUNTIME_ENV_FILE,
        (
            f"M8FLOW_VAULT_ADDR={VAULT_ADDR}\n"
            f"M8FLOW_VAULT_MOUNT_POINT={MOUNT_POINT}\n"
            f"M8FLOW_VAULT_SECRET_PATH_PREFIX={PATH_PREFIX}\n"
            f"M8FLOW_VAULT_APPROLE_MOUNT_POINT={APPROLE_MOUNT_POINT}\n"
            f"M8FLOW_VAULT_TENANT_POLICY_PREFIX={TENANT_POLICY_PREFIX}\n"
            f"M8FLOW_VAULT_TENANT_ROLE_PREFIX={TENANT_ROLE_PREFIX}\n"
            f"M8FLOW_VAULT_ROLE_ID_FILE={ROLE_ID_FILE.as_posix()}\n"
            f"M8FLOW_VAULT_SECRET_ID_FILE={SECRET_ID_FILE.as_posix()}\n"
        ),
        mode=0o644,
    )


def default_demo_bootstrap_secret_spec() -> SeededSecretSpec:
    ensure_backend_src_on_path()

    from m8flow_backend.config import default_organization_alias
    from m8flow_backend.startup.shared_realm_bootstrap import resolve_default_shared_realm_tenant_id

    organization_alias = (os.getenv("M8FLOW_VAULT_DEMO_DEFAULT_TENANT_ALIAS") or default_organization_alias()).strip()
    if not organization_alias:
        fail("The Vault demo default organization alias is not configured.")

    organization_id = resolve_default_shared_realm_tenant_id()
    if isinstance(organization_id, str) and organization_id.strip():
        return default_seeded_secret_spec(
            organization_alias=organization_alias,
            organization_id=organization_id.strip(),
        )

    demo_identity = wait_for_demo_tenant_identity(
        timeout_seconds=WAIT_TIMEOUT_SECONDS,
        interval_seconds=WAIT_INTERVAL_SECONDS,
        organization_alias=organization_alias,
    )
    return default_seeded_secret_spec(
        organization_alias=demo_identity.organization_alias,
        organization_id=demo_identity.organization_id,
    )


def load_seeded_secrets() -> list[SeededSecretSpec]:
    if not SECRETS_FILE.exists():
        log_missing_secrets_file_notice(format_missing_secrets_file_message(SECRETS_FILE))
        return [default_demo_bootstrap_secret_spec()]

    demo_identity = wait_for_demo_tenant_identity(
        timeout_seconds=WAIT_TIMEOUT_SECONDS,
        interval_seconds=WAIT_INTERVAL_SECONDS,
    )
    return load_seeded_secret_specs(
        SECRETS_FILE,
        organization_alias=demo_identity.organization_alias,
        organization_id=demo_identity.organization_id,
        missing_file_message_factory=format_missing_secrets_file_message,
        logger=log_missing_secrets_file_notice,
    )


def verification_target_secret(secrets: list[SeededSecretSpec]) -> SeededSecretSpec:
    if secrets:
        return secrets[0]
    return default_demo_bootstrap_secret_spec()


def secret_api_path(logical_path: str) -> str:
    return f"{parse.quote(MOUNT_POINT, safe='')}/data/{parse.quote(logical_path, safe='/')}"


def read_secret_value(secret: SeededSecretSpec, token: str, *, allow_missing: bool = False) -> str | None:
    status_code, payload, _body = vault_request(
        "GET",
        secret_api_path(seeded_secret_logical_path(secret)),
        token=token,
        expected_statuses=(200, 404) if allow_missing else (200,),
    )
    if status_code == 404:
        return None
    value = (((payload or {}).get("data") or {}).get("data") or {}).get("value")
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def write_secret_value(secret: SeededSecretSpec, token: str) -> None:
    vault_request(
        "POST",
        secret_api_path(seeded_secret_logical_path(secret)),
        token=token,
        payload={"data": {"value": secret.value}},
        expected_statuses=(200,),
    )


def seed_demo_secrets(root_token: str, secrets: list[SeededSecretSpec]) -> tuple[int, int]:
    written = 0
    skipped = 0

    for secret in secrets:
        existing_value = read_secret_value(secret, root_token, allow_missing=True)
        if existing_value is not None and not DEMO_OVERWRITE:
            skipped += 1
            continue

        write_secret_value(secret, root_token)
        written += 1

    return written, skipped


def write_verification_report(
    *,
    broker_direct_read_blocked: bool,
) -> None:
    write_plain_json_file(
        VERIFICATION_FILE,
        {
            "broker_direct_read_blocked": broker_direct_read_blocked,
            "verified": True,
        },
        mode=0o644,
    )


def verify_bootstrap(secrets: list[SeededSecretSpec]) -> None:
    status = wait_for_vault_status()
    if status.get("initialized") is not True or status.get("sealed") is not False:
        fail("Vault demo verification failed because Vault is not ready.")

    verified_secret = verification_target_secret(secrets)

    ensure_backend_src_on_path()

    os.environ["M8FLOW_VAULT_ADDR"] = VAULT_ADDR
    os.environ["M8FLOW_VAULT_MOUNT_POINT"] = MOUNT_POINT
    os.environ["M8FLOW_VAULT_SECRET_PATH_PREFIX"] = PATH_PREFIX
    os.environ["M8FLOW_VAULT_APPROLE_MOUNT_POINT"] = APPROLE_MOUNT_POINT
    os.environ["M8FLOW_VAULT_TENANT_POLICY_PREFIX"] = TENANT_POLICY_PREFIX
    os.environ["M8FLOW_VAULT_TENANT_ROLE_PREFIX"] = TENANT_ROLE_PREFIX
    os.environ["M8FLOW_VAULT_ROLE_ID_FILE"] = ROLE_ID_FILE.as_posix()
    os.environ["M8FLOW_VAULT_SECRET_ID_FILE"] = SECRET_ID_FILE.as_posix()
    os.environ.pop("M8FLOW_VAULT_TOKEN", None)
    os.environ.pop("VAULT_TOKEN", None)

    from m8flow_backend.services.tenant_scoped_vault_client_provider import TenantScopedVaultClientProvider
    from m8flow_backend.services.tenant_vault_provisioning_service import TenantVaultProvisioningService
    from m8flow_backend.services.vault_client import VaultClient, VaultClientError, VaultSettings

    broker_client = VaultClient(settings=VaultSettings.from_env())
    if not broker_client.check_availability():
        fail("Vault demo verification failed because the backend Vault client wrapper reported Vault unavailable.")

    TenantVaultProvisioningService(vault_client=broker_client).provision_tenant_identity(verified_secret.tenant_id)
    logical_path = f"tenants/{verified_secret.tenant_id}/secrets/{verified_secret.secret_name}"

    broker_direct_read_blocked = False
    try:
        broker_value = broker_client.retrieve_secret(logical_path)
    except VaultClientError:
        broker_direct_read_blocked = True
    else:
        if broker_value is None:
            broker_direct_read_blocked = True
        else:
            fail(
                f"Vault demo verification failed because the broker AppRole "
                f"'{BROKER_APPROLE_NAME}' can still read '{logical_path}' directly."
            )

    tenant_client = TenantScopedVaultClientProvider(broker_vault_client=broker_client).for_tenant(
        verified_secret.tenant_id
    )
    wrapper_value = tenant_client.vault_client.retrieve_secret(logical_path)
    if wrapper_value != verified_secret.value:
        fail(
            f"Vault demo verification failed for tenant-scoped backend wrapper path '{logical_path}'."
        )

    write_verification_report(
        broker_direct_read_blocked=broker_direct_read_blocked,
    )


def main() -> int:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        status = wait_for_vault_status()
        status = initialize_if_needed(status)
        status = unseal_if_needed(status)
        if status.get("sealed") is True:
            fail("Vault is still sealed after the development bootstrap flow.")
        wait_for_active_node()

        init_payload = load_init_payload()
        root_token = root_token_from_init(init_payload)

        ensure_kv_v2_mount(root_token)
        ensure_approle_auth(root_token)
        ensure_policy(root_token)
        ensure_approle_role(root_token)

        role_id = read_role_id(root_token)
        secret_id = ensure_secret_id(root_token, role_id)
        write_runtime_files(role_id, secret_id)

        seeded_secrets = load_seeded_secrets()
        seed_demo_secrets(root_token, seeded_secrets)
        verify_bootstrap(seeded_secrets)

        print("vault-demo: Bootstrap complete", flush=True)
        return 0
    except Exception as exc:
        print(
            f"vault-demo: Bootstrap failed: {format_bootstrap_failure_message(exc)}",
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
