#!/usr/bin/env python3
"""Bootstrap a disposable, local-development Vault for M8Flow Compose."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import time
from urllib import error, parse, request

ADDR = os.getenv("M8FLOW_VAULT_INTERNAL_ADDR", "http://vault:8200").rstrip("/")
ADMIN_STATE = Path(os.getenv("M8FLOW_VAULT_ADMIN_STATE_DIR", "/vault/admin"))
LEGACY_STATE = Path(os.getenv("M8FLOW_VAULT_LEGACY_STATE_DIR", "/vault/legacy-demo"))
SEED_STATE = Path(os.getenv("M8FLOW_VAULT_DEMO_STATE_DIR", "/vault/demo"))
RUNTIME = Path(os.getenv("M8FLOW_VAULT_RUNTIME_DIR", "/vault/runtime"))
MOUNT = os.getenv("M8FLOW_VAULT_MOUNT_POINT", "kv").strip("/")
APPROLE = os.getenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle").strip("/")
POLICY = os.getenv("M8FLOW_VAULT_POLICY_NAME", "m8flow")
ROLE = os.getenv("M8FLOW_VAULT_APPROLE_NAME", "m8flow")
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

    broker_policy = f'''path "sys/policies/acl/{POLICY_PREFIX}-*" {{ capabilities = ["create", "read", "update"] }}
path "sys/policy/{POLICY_PREFIX}-*" {{ capabilities = ["create", "read", "update"] }}
path "auth/{APPROLE}/role/{ROLE_PREFIX}-*" {{ capabilities = ["create", "read", "update"] }}
path "auth/{APPROLE}/role/{ROLE_PREFIX}-*/role-id" {{ capabilities = ["read"] }}
path "auth/{APPROLE}/role/{ROLE_PREFIX}-*/secret-id" {{ capabilities = ["create", "update"] }}
'''
    call("PUT", f"sys/policies/acl/{parse.quote(POLICY, safe='')}", token=root_token,
         payload={"policy": broker_policy}, expected=(200, 204))
    call("POST", f"auth/{APPROLE}/role/{parse.quote(ROLE, safe='')}", token=root_token,
         payload={"token_policies": [POLICY], "token_no_default_policy": True}, expected=(200, 204))
    _code, role_payload = call("GET", f"auth/{APPROLE}/role/{parse.quote(ROLE, safe='')}/role-id", token=root_token)
    role_id = role_payload.get("data", {}).get("role_id")
    _code, secret_payload = call("POST", f"auth/{APPROLE}/role/{parse.quote(ROLE, safe='')}/secret-id", token=root_token, payload={})
    secret_id = secret_payload.get("data", {}).get("secret_id")
    if not role_id or not secret_id:
        raise RuntimeError("Vault did not return broker AppRole credentials.")

    # The seed job receives only this short-lived, path-scoped token. Keep the
    # root token and init keys in ADMIN_STATE, which is mounted only by this
    # bootstrap service.
    call(
        "PUT",
        f"sys/policies/acl/{parse.quote(SEED_POLICY, safe='')}",
        token=root_token,
        payload={"policy": _seed_policy()},
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

    RUNTIME.mkdir(parents=True, exist_ok=True)
    role_file, secret_file = RUNTIME / "m8flow-role-id", RUNTIME / "m8flow-secret-id"
    for file, value in ((role_file, role_id), (secret_file, secret_id)):
        file.write_text(value + "\n", encoding="utf-8")
        os.chmod(file, 0o600)
        # The backend drops to UID 1000 before reading these configured files.
        os.chown(file, 1000, 1000)
    runtime = RUNTIME / "runtime.env"
    runtime.write_text(
        f"M8FLOW_VAULT_ADDR={ADDR}\n"
        f"M8FLOW_VAULT_MOUNT_POINT={MOUNT}\n"
        f"M8FLOW_VAULT_SECRET_PATH_PREFIX={PATH_PREFIX}\n"
        f"M8FLOW_VAULT_APPROLE_MOUNT_POINT={APPROLE}\n"
        f"M8FLOW_VAULT_TENANT_POLICY_PREFIX={POLICY_PREFIX}\n"
        f"M8FLOW_VAULT_TENANT_ROLE_PREFIX={ROLE_PREFIX}\n"
        f"M8FLOW_VAULT_ROLE_ID_FILE={role_file}\n"
        f"M8FLOW_VAULT_SECRET_ID_FILE={secret_file}\n", encoding="utf-8")
    os.chmod(runtime, 0o600)
    # Older Compose versions put init.json in the shared demo-state volume.
    # Once migrated, remove that root credential from the volume used only as
    # a legacy bootstrap source. vault-seed never mounts this volume.
    if legacy_init_file.exists():
        legacy_init_file.unlink()
    print(
        "vault-demo: local Vault is initialized; broker credentials and a scoped "
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
