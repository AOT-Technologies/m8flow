#!/usr/bin/env python3
"""Bootstrap a disposable, local-development Vault for M8Flow Compose."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib import error, parse, request

ADDR = os.getenv("M8FLOW_VAULT_INTERNAL_ADDR", "http://vault:8200").rstrip("/")
ADMIN_STATE = Path(os.getenv("M8FLOW_VAULT_ADMIN_STATE_DIR", "/vault/admin"))
LEGACY_STATE = Path(os.getenv("M8FLOW_VAULT_LEGACY_STATE_DIR", "/vault/legacy-demo"))
SEED_STATE = Path(os.getenv("M8FLOW_VAULT_DEMO_STATE_DIR", "/vault/demo"))
RUNTIME = Path(os.getenv("M8FLOW_VAULT_RUNTIME_DIR", "/vault/runtime"))
PROVISIONER = Path(os.getenv("M8FLOW_VAULT_PROVISIONER_DIR", "/vault/provisioner"))
MOUNT = os.getenv("M8FLOW_VAULT_MOUNT_POINT", "kv").strip("/")
APPROLE = os.getenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle").strip("/")
POLICY = os.getenv("M8FLOW_VAULT_POLICY_NAME", "m8flow")
ROLE = os.getenv("M8FLOW_VAULT_APPROLE_NAME", "m8flow")
RUNTIME_POLICY = os.getenv("M8FLOW_VAULT_RUNTIME_POLICY_NAME", "m8flow-runtime")
RUNTIME_ROLE = os.getenv("M8FLOW_VAULT_RUNTIME_APPROLE_NAME", "m8flow-runtime")
POLICY_PREFIX = os.getenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
ROLE_PREFIX = os.getenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
PATH_PREFIX = os.getenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow").strip("/")
DEMO_TENANT_ID = os.getenv("M8FLOW_VAULT_DEMO_TENANT_ID", "m8flow")
SEED_POLICY = os.getenv("M8FLOW_VAULT_DEMO_SEED_POLICY_NAME", "m8flow-demo-seed")
TIMEOUT = int(os.getenv("M8FLOW_VAULT_DEMO_WAIT_TIMEOUT_SECONDS", "180"))
_POLICY_COMPONENT = re.compile(r"^[A-Za-z0-9_-]+$")


def _seed_policy() -> str:
    """Allow the seeder to manage only named-value secrets for the demo tenant."""
    components = [MOUNT, *PATH_PREFIX.split("/"), DEMO_TENANT_ID]
    if any(not _POLICY_COMPONENT.fullmatch(component) for component in components):
        raise RuntimeError("Vault demo mount, path prefix, and tenant ID must be safe path components.")
    path = (
        f"{MOUNT}/data/{PATH_PREFIX}/tenants/{DEMO_TENANT_ID}/"
        "secrets/configuration-variable/*"
    )
    metadata_path = path.replace("/data/", "/metadata/", 1)
    return (
        f'path "{path}" {{ capabilities = ["create", "read", "update"] }}\n'
        f'path "{metadata_path}" {{ capabilities = ["delete"] }}\n'
    )


def _validate_policy_identifiers() -> str:
    """Validate environment-controlled identifiers before any Vault writes."""
    for label, value in (
        ("policy name", POLICY),
        ("AppRole name", ROLE),
        ("runtime policy name", RUNTIME_POLICY),
        ("runtime AppRole name", RUNTIME_ROLE),
        ("tenant policy prefix", POLICY_PREFIX),
        ("tenant role prefix", ROLE_PREFIX),
    ):
        if not _POLICY_COMPONENT.fullmatch(value):
            raise RuntimeError(
                f"Vault demo {label} must contain only letters, numbers, underscores, and hyphens."
            )

    approle_components = APPROLE.split("/")
    if any(not _POLICY_COMPONENT.fullmatch(component) for component in approle_components):
        raise RuntimeError(
            "Vault demo AppRole mount must contain only safe path components "
            "(letters, numbers, underscores, and hyphens)."
        )

    # Validate all values used in policy paths before bootstrap mutates Vault.
    return _seed_policy()


def _set_runtime_file_owner(file: Path) -> None:
    """Set ownership expected by the backend and explain platform failures."""
    try:
        os.chown(file, 1000, 1000)
    except (AttributeError, NotImplementedError, OSError) as exc:
        raise RuntimeError(
            f"Could not set ownership of Vault runtime credential file {file} "
            "to UID/GID 1000. Run the bootstrap in a Linux container with a "
            "compatible UID mapping."
        ) from exc


def call(method: str, path: str, *, token: str | None = None, payload: object | None = None,
         expected: tuple[int, ...] = (200,)) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
    body = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(f"{ADDR}/v1/{path.lstrip('/')}", data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=10) as response:
            code, data = response.status, response.read()
    except error.HTTPError as exc:
        code, data = exc.code, exc.read()
    except error.URLError as exc:
        raise RuntimeError(f"Vault request failed for {method} {path}: {exc.reason}") from exc
    try:
        parsed = json.loads(data) if data else {}
    except json.JSONDecodeError:
        parsed = {}
    if code not in expected:
        details = "; ".join(str(item) for item in parsed.get("errors", []))
        message = f"Vault request {method} {path} returned HTTP {code}"
        if details:
            message += f": {details}"
        raise RuntimeError(f"{message}.")
    return code, parsed


def wait_status() -> dict:
    deadline = time.monotonic() + TIMEOUT
    last_error = "Vault has not responded yet."
    while time.monotonic() < deadline:
        try:
            _code, result = call("GET", "sys/health?standbyok=true&perfstandbyok=true", expected=(200, 429, 472, 473, 501, 503))
            return result
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(2)
    raise RuntimeError(f"Timed out waiting for local Vault: {last_error}")


def wait_for_admin_api(token: str, path: str) -> dict:
    """Wait for Vault's single-node Raft instance to finish leadership election."""
    deadline = time.monotonic() + TIMEOUT
    last_error = "Vault's active node is not ready yet."
    while time.monotonic() < deadline:
        try:
            _code, result = call("GET", path, token=token)
            return result
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for Vault admin API: {last_error}")


def main() -> int:
    seed_policy = _validate_policy_identifiers()
    ADMIN_STATE.mkdir(parents=True, exist_ok=True)
    SEED_STATE.mkdir(parents=True, exist_ok=True)
    init_file = ADMIN_STATE / "init.json"
    legacy_init_file = LEGACY_STATE / "init.json"
    status = wait_status()
    if status.get("initialized") is False:
        _code, result = call("PUT", "sys/init", payload={"secret_shares": 1, "secret_threshold": 1})
        init_file.write_text(json.dumps(result), encoding="utf-8")
        os.chmod(init_file, 0o600)
    elif not init_file.exists():
        if not legacy_init_file.exists():
            raise RuntimeError(
                "Vault is initialized but local admin init state is missing. "
                "Restore its admin state or reset the local Vault volumes."
            )
        init_file.write_text(legacy_init_file.read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(init_file, 0o600)
    init_data = json.loads(init_file.read_text(encoding="utf-8"))
    root_token = init_data.get("root_token")
    keys = init_data.get("keys_base64") or init_data.get("unseal_keys_b64") or []
    if not root_token or not keys:
        raise RuntimeError("Local Vault init state is incomplete.")
    status = wait_status()
    if status.get("sealed") is True:
        _code, status = call("PUT", "sys/unseal", payload={"key": keys[0]})
    if status.get("sealed") is True:
        raise RuntimeError("Local Vault remains sealed after the development unseal step.")

    mounts = wait_for_admin_api(root_token, "sys/mounts")
    if f"{MOUNT}/" not in mounts:
        call("POST", f"sys/mounts/{parse.quote(MOUNT, safe='')}", token=root_token,
             payload={"type": "kv", "options": {"version": "2"}}, expected=(200, 204))
    _code, methods = call("GET", "sys/auth", token=root_token)
    if f"{APPROLE}/" not in methods:
        call("POST", f"sys/auth/{parse.quote(APPROLE, safe='')}", token=root_token,
             payload={"type": "approle"}, expected=(200, 204))

    provisioner_policy = f'''path "sys/policies/acl/{POLICY_PREFIX}-*" {{ capabilities = ["create", "read", "update"] }}
path "sys/policy/{POLICY_PREFIX}-*" {{ capabilities = ["create", "read", "update"] }}
path "auth/{APPROLE}/role/{ROLE_PREFIX}-*" {{ capabilities = ["create", "read", "update"] }}
path "auth/{APPROLE}/role/{ROLE_PREFIX}-*/role-id" {{ capabilities = ["read"] }}
'''
    runtime_policy = f'''path "auth/{APPROLE}/role/{ROLE_PREFIX}-*/role-id" {{ capabilities = ["read"] }}
path "auth/{APPROLE}/role/{ROLE_PREFIX}-*/secret-id" {{ capabilities = ["create", "update"] }}
path "auth/{APPROLE}/role/{ROLE_PREFIX}-*/secret-id/destroy" {{ capabilities = ["update"] }}
path "auth/{APPROLE}/role/{ROLE_PREFIX}-*/secret-id-accessor/destroy" {{ capabilities = ["update"] }}
'''
    call("PUT", f"sys/policies/acl/{parse.quote(POLICY, safe='')}", token=root_token,
         payload={"policy": provisioner_policy}, expected=(200, 204))
    call("PUT", f"sys/policies/acl/{parse.quote(RUNTIME_POLICY, safe='')}", token=root_token,
         payload={"policy": runtime_policy}, expected=(200, 204))

    RUNTIME.mkdir(parents=True, exist_ok=True)
    PROVISIONER.mkdir(parents=True, exist_ok=True)
    runtime_role_file = RUNTIME / "runtime-role-id"
    runtime_secret_file = RUNTIME / "runtime-secret-id"
    provisioner_api_file = RUNTIME / "provisioner-api-token"
    provisioner_role_file = PROVISIONER / "provisioner-role-id"
    provisioner_secret_file = PROVISIONER / "provisioner-secret-id"
    provisioner_service_api_file = PROVISIONER / "provisioner-api-token"

    def ensure_workload_approle(
        role_name: str,
        policy_name: str,
        secret_id_files: tuple[Path, ...],
    ) -> tuple[str, str]:
        call(
            "POST",
            f"auth/{APPROLE}/role/{parse.quote(role_name, safe='')}",
            token=root_token,
            payload={
                "token_policies": [policy_name],
                "token_no_default_policy": True,
                "secret_id_num_uses": 0,
                "secret_id_ttl": 0,
                "token_ttl": "15m",
                "token_max_ttl": "1h",
            },
            expected=(200, 204),
        )
        _code, role_payload = call(
            "GET",
            f"auth/{APPROLE}/role/{parse.quote(role_name, safe='')}/role-id",
            token=root_token,
        )
        role_id = role_payload.get("data", {}).get("role_id")
        secret_id = None
        for secret_id_file in secret_id_files:
            try:
                candidate = secret_id_file.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not candidate:
                continue
            lookup_code, _lookup_payload = call(
                "POST",
                f"auth/{APPROLE}/role/{parse.quote(role_name, safe='')}/secret-id/lookup",
                token=root_token,
                payload={"secret_id": candidate},
                expected=(200, 400, 404),
            )
            if lookup_code == 200:
                secret_id = candidate
                break
        if secret_id is None:
            _code, secret_payload = call(
                "POST",
                f"auth/{APPROLE}/role/{parse.quote(role_name, safe='')}/secret-id",
                token=root_token,
                payload={},
            )
            secret_id = secret_payload.get("data", {}).get("secret_id")
        if not role_id or not secret_id:
            raise RuntimeError(f"Vault did not return credentials for AppRole {role_name}.")
        return role_id, secret_id

    runtime_role_id, runtime_secret_id = ensure_workload_approle(
        RUNTIME_ROLE, RUNTIME_POLICY, (runtime_secret_file,)
    )
    provisioner_secret_candidates = [provisioner_secret_file]
    if ROLE == "m8flow":
        # The previous local broker role used this credential path. Reuse it
        # as the provisioner credential during upgrade instead of orphaning it.
        provisioner_secret_candidates.append(RUNTIME / "m8flow-secret-id")
    provisioner_role_id, provisioner_secret_id = ensure_workload_approle(
        ROLE, POLICY, tuple(provisioner_secret_candidates)
    )
    provisioner_api_token = secrets.token_urlsafe(48)

    # The seed job receives only this short-lived, path-scoped token. Keep the
    # root token and init keys in ADMIN_STATE, which is mounted only by this
    # bootstrap service.
    call(
        "PUT",
        f"sys/policies/acl/{parse.quote(SEED_POLICY, safe='')}",
        token=root_token,
        payload={"policy": seed_policy},
        expected=(200, 204),
    )
    _code, seed_token_payload = call(
        "POST",
        "auth/token/create-orphan",
        token=root_token,
        payload={
            "policies": [SEED_POLICY],
            "no_default_policy": True,
            "renewable": False,
            # Covers the seed job's bounded health wait plus seeding time.
            "ttl": "15m",
        },
    )
    seed_token = seed_token_payload.get("auth", {}).get("client_token")
    if not seed_token:
        raise RuntimeError("Vault did not return a scoped demo-seed token.")
    seed_token_file = SEED_STATE / "seed-token"
    seed_token_file.write_text(seed_token + "\n", encoding="utf-8")
    os.chmod(seed_token_file, 0o600)

    # Remove the broad broker env file written by older local bootstrap runs.
    # The new runtime volume uses explicit runtime-only credential files.
    legacy_runtime_env = RUNTIME / "runtime.env"
    if legacy_runtime_env.exists():
        legacy_runtime_env.unlink()
    for file, value in (
        (runtime_role_file, runtime_role_id),
        (runtime_secret_file, runtime_secret_id),
        (provisioner_api_file, provisioner_api_token),
        (provisioner_role_file, provisioner_role_id),
        (provisioner_secret_file, provisioner_secret_id),
        (provisioner_service_api_file, provisioner_api_token),
    ):
        file.write_text(value + "\n", encoding="utf-8")
        os.chmod(file, 0o600)
        # The backend drops to UID 1000 before reading these configured files.
        _set_runtime_file_owner(file)
    for legacy_file in (RUNTIME / "m8flow-role-id", RUNTIME / "m8flow-secret-id"):
        if legacy_file.exists():
            legacy_file.unlink()
    # Older Compose versions put init.json in the shared demo-state volume.
    # Once migrated, remove that root credential from the volume used only as
    # a legacy bootstrap source. vault-seed never mounts this volume.
    if legacy_init_file.exists():
        legacy_init_file.unlink()
    print(
        "vault-demo: local Vault is initialized; runtime and provisioner credentials plus a scoped "
        "demo-seed token are ready. Demo seeding waits for backend health.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"vault-demo: bootstrap failed: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
