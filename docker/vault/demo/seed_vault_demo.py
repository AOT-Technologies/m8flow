#!/usr/bin/env python3
"""Seed configured local demo secrets after the backend has completed migrations."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, parse, request

import psycopg
import yaml

ADDR = os.getenv("M8FLOW_VAULT_INTERNAL_ADDR", "http://vault:8200").rstrip("/")
STATE = Path(os.getenv("M8FLOW_VAULT_DEMO_STATE_DIR", "/vault/demo"))
SECRETS = Path(os.getenv("M8FLOW_VAULT_DEMO_SECRETS_FILE", "/app/docker/vault/demo/secrets.yml"))
MOUNT = os.getenv("M8FLOW_VAULT_MOUNT_POINT", "kv").strip("/")
PREFIX = os.getenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow").strip("/")
OVERWRITE = os.getenv("M8FLOW_VAULT_DEMO_OVERWRITE", "false").lower() in {"1", "true", "yes", "on"}


def vault_call(method: str, path: str, token: str, payload: object | None = None,
               expected: tuple[int, ...] = (200,)) -> tuple[int, dict]:
    headers = {"X-Vault-Token": token, "Content-Type": "application/json"}
    body = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(f"{ADDR}/v1/{path.lstrip('/')}", data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=10) as response:
            code, data = response.status, response.read()
    except error.HTTPError as exc:
        code, data = exc.code, exc.read()
    parsed = json.loads(data) if data else {}
    if code not in expected:
        raise RuntimeError(f"Vault {method} {path} returned HTTP {code}.")
    return code, parsed


def tenant_id_from_database() -> str:
    uri = os.environ["M8FLOW_BACKEND_DATABASE_URI"].replace("postgresql+psycopg://", "postgresql://", 1)
    alias = os.getenv("M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS", "m8flow").strip() or "m8flow"
    with psycopg.connect(uri, connect_timeout=10) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT id::text FROM m8flow_tenant WHERE slug = %s", (alias,))
        row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"The migrated backend database has no tenant with default alias {alias!r}.")
    return str(row[0])


def seed() -> tuple[int, int]:
    if not SECRETS.exists():
        print(f"vault-seed: no local seed file at {SECRETS}; skipping demo secret seeding.", flush=True)
        return 0, 0
    payload = yaml.safe_load(SECRETS.read_text(encoding="utf-8")) or {}
    tenants = payload.get("tenants", {}) if isinstance(payload, dict) else {}
    if not isinstance(tenants, dict):
        raise RuntimeError("The demo secrets file must contain a tenants mapping.")
    tenant_id = tenant_id_from_database()
    init_file = STATE / "init.json"
    if not init_file.exists():
        raise RuntimeError("Vault local init state is missing; run vault-demo first.")
    root_token = json.loads(init_file.read_text(encoding="utf-8")).get("root_token")
    if not root_token:
        raise RuntimeError("Vault local init state has no root token.")
    written = skipped = 0
    for tenant_ref, tenant_data in tenants.items():
        if str(tenant_ref) not in {"m8flow", os.getenv("M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS", "m8flow")}:
            raise RuntimeError("Local demo seeding currently supports only the default m8flow tenant alias.")
        secrets = tenant_data.get("secrets", tenant_data) if isinstance(tenant_data, dict) else None
        if not isinstance(secrets, dict):
            raise RuntimeError(f"Secrets for tenant {tenant_ref!r} must be a mapping.")
        for name, value in secrets.items():
            secret_name = str(name).strip()
            if not secret_name or "/" in secret_name or not isinstance(value, (str, int, float, bool)):
                raise RuntimeError(f"Invalid demo secret entry for {tenant_ref!r}.")
            logical = f"{PREFIX}/tenants/{tenant_id}/secrets/{secret_name}"
            path = f"{parse.quote(MOUNT, safe='')}/data/{parse.quote(logical, safe='/')}"
            status, _ = vault_call("GET", path, root_token, expected=(200, 404))
            if status == 200 and not OVERWRITE:
                skipped += 1
                continue
            vault_call("POST", path, root_token, {"data": {"value": str(value)}})
            written += 1
    print(f"vault-seed: seeded {written} local demo secret(s); preserved {skipped} existing secret(s).", flush=True)
    return written, skipped


if __name__ == "__main__":
    try:
        seed()
    except Exception as exc:
        raise SystemExit(f"vault-seed: failed: {exc}")
