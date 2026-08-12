#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from demo_identity import wait_for_demo_tenant_identity
from seeded_secrets import SeededSecretSpec, load_seeded_secret_specs


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
STATE_DIR = Path(os.getenv("M8FLOW_VAULT_DEMO_STATE_DIR") or "/vault/demo")
INIT_FILE = STATE_DIR / "init.json"
ROLE_ID_FILE = STATE_DIR / "m8flow-role-id"
SECRET_ID_FILE = STATE_DIR / "m8flow-secret-id"
APPROLE_ENV_FILE = STATE_DIR / "m8flow-approle.env"
RUNTIME_ENV_FILE = STATE_DIR / "runtime.env"
VERIFICATION_FILE = STATE_DIR / "verification.json"
SECRETS_FILE = Path(os.getenv("M8FLOW_VAULT_DEMO_SECRETS_FILE") or "/app/docker/vault/demo/secrets.yml")
SECRETS_SAMPLE_FILE = Path("/app/docker/vault/demo/secrets.yml.sample")
POLICY_TEMPLATE = Path(
    os.getenv("M8FLOW_VAULT_POLICY_TEMPLATE") or "/app/docker/vault/policies/m8flow-policy.hcl.tpl"
)
HEALTH_PATH = "sys/health?standbyok=true&perfstandbyok=true"
LEADER_PATH = "sys/leader"


def log(message: str) -> None:
    print(f"vault-demo: {message}", flush=True)


def fail(message: str) -> None:
    raise RuntimeError(message)


def write_text_file(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def write_json_file(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    write_text_file(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", mode=mode)


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def format_missing_secrets_file_message(path: Path) -> str:
    message = f"Vault demo secrets file is missing: {path}"
    if path.name == "secrets.yml":
        message += (
            f". Copy {SECRETS_SAMPLE_FILE} to {path} and edit the local values you want "
            "seeded for the m8flow tenant."
        )
    return message


def seeded_secret_logical_path(secret: SeededSecretSpec) -> str:
    return f"{PATH_PREFIX}/tenants/{secret.tenant_id}/secrets/{secret.secret_name}"


def remove_generated_files() -> None:
    for path in (ROLE_ID_FILE, SECRET_ID_FILE, APPROLE_ENV_FILE, RUNTIME_ENV_FILE, VERIFICATION_FILE):
        path.unlink(missing_ok=True)


def vault_request(
    method: str,
    api_path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
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
        with request.urlopen(req, timeout=10) as response:
            response_status = int(response.getcode())
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        response_status = int(exc.code)
        response_body = exc.read().decode("utf-8")
    except error.URLError as exc:
        fail(f"Could not reach Vault at {VAULT_ADDR}: {exc}")

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
            f"Response: {response_body or '<empty>'}"
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
        except RuntimeError as exc:
            last_error = str(exc)
        time.sleep(WAIT_INTERVAL_SECONDS)

    fail(f"Timed out waiting for Vault health at {VAULT_ADDR}. Last error: {last_error or 'unknown error'}")


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
                last_error = f"leader not active yet: {payload}"
            elif "active cluster node not found" in body:
                last_error = body
            else:
                last_error = "leader endpoint returned a non-JSON response"
        except RuntimeError as exc:
            if "active cluster node not found" in str(exc):
                last_error = str(exc)
            else:
                last_error = str(exc)
        time.sleep(WAIT_INTERVAL_SECONDS)

    fail(
        f"Timed out waiting for the local Vault node to become active at {VAULT_ADDR}. "
        f"Last error: {last_error or 'unknown error'}"
    )


def load_init_payload() -> dict[str, Any]:
    if not INIT_FILE.exists():
        fail(
            "Vault is already initialized, but the persisted demo init file is missing. "
            "Reset both the Vault data volume and the vault-demo state volume, then retry."
        )
    return load_json_file(INIT_FILE)


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

    log("Vault is uninitialized. Initializing a development-only instance.")
    remove_generated_files()
    _status_code, payload, _body = vault_request(
        "PUT",
        "sys/init",
        payload={"secret_shares": 1, "secret_threshold": 1},
        expected_statuses=(200,),
    )
    if not isinstance(payload, dict):
        fail("Vault init did not return a JSON payload.")
    write_json_file(INIT_FILE, payload)
    return wait_for_vault_status()


def unseal_if_needed(status: dict[str, Any]) -> dict[str, Any]:
    if status.get("sealed") is not True:
        return status

    init_payload = load_init_payload()
    log("Vault is sealed. Unsealing with the persisted development key.")
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
        log(f"Enabling KV v2 mount '{MOUNT_POINT}'.")
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

    log(f"Enabling the AppRole auth method at mount '{APPROLE_MOUNT_POINT}'.")
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
    log(f"Creating or updating broker AppRole '{BROKER_APPROLE_NAME}' with policy '{BROKER_POLICY_NAME}'.")
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
        existing_secret_id = SECRET_ID_FILE.read_text(encoding="utf-8").strip()
        if existing_secret_id:
            try:
                approle_login(role_id, existing_secret_id)
                log("Reusing the persisted broker AppRole secret_id.")
                return existing_secret_id
            except RuntimeError as exc:
                log(f"Persisted broker AppRole secret_id is invalid; generating a fresh one. Detail: {exc}")

    log("Generating a persisted broker AppRole secret_id for development use.")
    return generate_secret_id(root_token)


def write_runtime_files(role_id: str, secret_id: str) -> None:
    write_text_file(ROLE_ID_FILE, role_id + "\n")
    write_text_file(SECRET_ID_FILE, secret_id + "\n")
    write_text_file(
        APPROLE_ENV_FILE,
        (
            f"M8FLOW_VAULT_ADDR={VAULT_ADDR}\n"
            f"M8FLOW_VAULT_MOUNT_POINT={MOUNT_POINT}\n"
            f"M8FLOW_VAULT_SECRET_PATH_PREFIX={PATH_PREFIX}\n"
            f"M8FLOW_VAULT_APPROLE_MOUNT_POINT={APPROLE_MOUNT_POINT}\n"
            f"M8FLOW_VAULT_TENANT_POLICY_PREFIX={TENANT_POLICY_PREFIX}\n"
            f"M8FLOW_VAULT_TENANT_ROLE_PREFIX={TENANT_ROLE_PREFIX}\n"
            f"M8FLOW_VAULT_ROLE_ID={role_id}\n"
            f"M8FLOW_VAULT_SECRET_ID={secret_id}\n"
        ),
    )
    write_text_file(
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


def load_seeded_secrets() -> list[SeededSecretSpec]:
    demo_identity = wait_for_demo_tenant_identity(
        timeout_seconds=WAIT_TIMEOUT_SECONDS,
        interval_seconds=WAIT_INTERVAL_SECONDS,
    )
    return load_seeded_secret_specs(
        SECRETS_FILE,
        organization_alias=demo_identity.organization_alias,
        organization_id=demo_identity.organization_id,
        missing_file_message_factory=format_missing_secrets_file_message,
        logger=log,
    )


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
    verified_secret: SeededSecretSpec,
    broker_direct_read_blocked: bool,
    tenant_policy_name: str,
    tenant_role_name: str,
    written: int,
    skipped: int,
) -> None:
    write_json_file(
        VERIFICATION_FILE,
        {
            "approle_mount_point": APPROLE_MOUNT_POINT,
            "approle_name": BROKER_APPROLE_NAME,
            "broker_approle_name": BROKER_APPROLE_NAME,
            "broker_direct_read_blocked": broker_direct_read_blocked,
            "broker_policy_name": BROKER_POLICY_NAME,
            "mount_point": MOUNT_POINT,
            "overwrite": DEMO_OVERWRITE,
            "path_prefix": PATH_PREFIX,
            "policy_name": BROKER_POLICY_NAME,
            "seeded_secret_count": written + skipped,
            "skipped": skipped,
            "tenant_policy_name": tenant_policy_name,
            "tenant_role_name": tenant_role_name,
            "verified_secret_tenant_id": verified_secret.tenant_id,
            "verified_secret_tenant_reference": verified_secret.tenant_reference,
            "verified_secret_path": seeded_secret_logical_path(verified_secret),
            "written": written,
        },
        mode=0o644,
    )


def verify_bootstrap(role_id: str, secret_id: str, secrets: list[SeededSecretSpec], written: int, skipped: int) -> None:
    if not secrets:
        fail("Vault demo verification requires at least one seeded secret.")

    status = wait_for_vault_status()
    if status.get("initialized") is not True or status.get("sealed") is not False:
        fail(f"Vault demo verification failed because Vault is not ready. Status: {status}")

    verified_secret = secrets[0]

    backend_src = Path("/app/m8flow-backend/src")
    backend_src_str = str(backend_src)
    if backend_src_str not in sys.path:
        sys.path.insert(0, backend_src_str)

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

    provisioned_identity = TenantVaultProvisioningService(vault_client=broker_client).provision_tenant_identity(
        verified_secret.tenant_id
    )
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
        verified_secret=verified_secret,
        broker_direct_read_blocked=broker_direct_read_blocked,
        tenant_policy_name=provisioned_identity.policy_name,
        tenant_role_name=provisioned_identity.role_name,
        written=written,
        skipped=skipped,
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
        written, skipped = seed_demo_secrets(root_token, seeded_secrets)
        verify_bootstrap(role_id, secret_id, seeded_secrets, written, skipped)

        log(
            "Bootstrap complete "
            f"(mount={MOUNT_POINT}, broker_policy={BROKER_POLICY_NAME}, broker_approle={BROKER_APPROLE_NAME}, "
            f"written={written}, skipped={skipped}, overwrite={DEMO_OVERWRITE})."
        )
        return 0
    except Exception as exc:
        print(f"vault-demo: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
