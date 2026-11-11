#!/usr/bin/env python3
"""Operator-controlled cleanup of one deleted tenant's Vault data and identity."""

from __future__ import annotations

import os
import re
import sys
from urllib import error, parse, request


def _safe_name(value: str, label: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    if not value:
        raise ValueError(f"{label} must contain a Vault-safe character.")
    return value


def _api(method: str, path: str, *, missing_ok: bool = False) -> dict | None:
    addr = os.environ["M8FLOW_VAULT_ADDR"].rstrip("/")
    token = os.environ.get("M8FLOW_VAULT_OPERATOR_TOKEN") or os.environ.get("VAULT_TOKEN")
    if not token:
        raise ValueError("Set M8FLOW_VAULT_OPERATOR_TOKEN or VAULT_TOKEN.")
    headers = {"X-Vault-Token": token}
    namespace = os.getenv("M8FLOW_VAULT_NAMESPACE")
    if namespace:
        headers["X-Vault-Namespace"] = namespace
    req = request.Request(
        f"{addr}/v1/{parse.quote(path.lstrip('/'), safe='/.-_+')}",
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=float(os.getenv("M8FLOW_VAULT_TIMEOUT_SECONDS", "5"))) as response:
            payload = response.read()
    except error.HTTPError as exc:
        if missing_ok and exc.code == 404:
            return None
        raise RuntimeError(f"Vault {method} {path} returned HTTP {exc.code}.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Vault request failed for {method} {path}.") from exc
    if not payload:
        return {}
    import json

    result = json.loads(payload)
    return result if isinstance(result, dict) else {}


def _delete_kv_tree(mount: str, path: str) -> None:
    metadata_path = f"{mount}/metadata/{path}"
    result = _api("LIST", metadata_path, missing_ok=True)
    keys = (result or {}).get("data", {}).get("keys", [])
    if keys:
        for name in keys:
            _delete_kv_tree(mount, f"{path.rstrip('/')}/{str(name).rstrip('/')}")
    else:
        _api("DELETE", metadata_path, missing_ok=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not re.fullmatch(r"[A-Za-z0-9._-]+", argv[1]):
        raise ValueError("Usage: delete_tenant_vault.py <tenant-id> (letters, digits, '.', '_' and '-' only).")
    tenant_id = argv[1]
    mount = _safe_name(os.getenv("M8FLOW_VAULT_MOUNT_POINT", "kv"), "KV mount")
    approle_mount = _safe_name(os.getenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle"), "AppRole mount")
    role_prefix = _safe_name(os.getenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role"), "role prefix")
    policy_prefix = _safe_name(os.getenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy"), "policy prefix")
    path_prefix = os.getenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow").strip("/")
    if not path_prefix or any(not re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in path_prefix.split("/")):
        raise ValueError("M8FLOW_VAULT_SECRET_PATH_PREFIX contains an invalid path component.")

    # Delete exact paths for this tenant only. Operator ACLs should be scoped to
    # the configured tenant prefixes whenever the Vault deployment supports it.
    _delete_kv_tree(mount, f"{path_prefix}/tenants/{tenant_id}/secrets")
    _api("DELETE", f"auth/{approle_mount}/role/{role_prefix}-{tenant_id}", missing_ok=True)
    _api("DELETE", f"sys/policy/{policy_prefix}-{tenant_id}", missing_ok=True)
    print(f"Vault data, AppRole, and policy removed for tenant {tenant_id}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception as exc:
        print(f"Vault tenant cleanup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
