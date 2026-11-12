#!/usr/bin/env python3
"""Seed configured local demo secrets after the backend has completed migrations."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from urllib import error, parse, request

import psycopg
from psycopg.types.json import Json
import yaml

ADDR = os.getenv("M8FLOW_VAULT_INTERNAL_ADDR", "http://vault:8200").rstrip("/")
STATE = Path(os.getenv("M8FLOW_VAULT_DEMO_STATE_DIR", "/vault/demo"))
SECRETS = Path(os.getenv("M8FLOW_VAULT_DEMO_SECRETS_FILE", "/app/docker/vault/demo/secrets.yml"))
MOUNT = os.getenv("M8FLOW_VAULT_MOUNT_POINT", "kv").strip("/")
PREFIX = os.getenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow").strip("/")
DEMO_TENANT_ID = os.getenv("M8FLOW_VAULT_DEMO_TENANT_ID", "m8flow")
OVERWRITE = os.getenv("M8FLOW_VAULT_DEMO_OVERWRITE", "false").lower() in {"1", "true", "yes", "on"}
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,255}$")


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


def wait_for_backend_health() -> None:
    health_url = os.getenv(
        "M8FLOW_VAULT_DEMO_BACKEND_HEALTH_URL",
        "http://m8flow-backend:6840/v1.0/healthy",
    )
    try:
        timeout_seconds = float(
            os.getenv("M8FLOW_VAULT_DEMO_BACKEND_HEALTH_TIMEOUT_SECONDS", "600")
        )
        poll_seconds = float(
            os.getenv("M8FLOW_VAULT_DEMO_BACKEND_HEALTH_POLL_SECONDS", "5")
        )
    except ValueError as exc:
        raise RuntimeError("Backend health wait timeout and poll interval must be numbers.") from exc
    if timeout_seconds <= 0 or poll_seconds <= 0:
        raise RuntimeError("Backend health wait timeout and poll interval must be positive.")

    deadline = time.monotonic() + timeout_seconds
    last_check = "no response received"
    print(
        f"vault-seed: waiting up to {timeout_seconds:g}s for backend health at {health_url}.",
        flush=True,
    )
    while True:
        try:
            with request.urlopen(health_url, timeout=min(5.0, timeout_seconds)) as response:
                if 200 <= response.status < 300:
                    print("vault-seed: backend is healthy; starting demo seed.", flush=True)
                    return
                last_check = f"HTTP {response.status}"
        except error.HTTPError as exc:
            last_check = f"HTTP {exc.code}"
        except (error.URLError, TimeoutError, OSError) as exc:
            # Keep diagnostics useful without echoing server response bodies.
            last_check = type(exc).__name__

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"Timed out waiting for backend health at {health_url} after "
                f"{timeout_seconds:g}s (last check: {last_check}). Check the "
                "m8flow-backend healthcheck and container logs."
            )
        time.sleep(min(poll_seconds, remaining))


def _variables_for_tenant(tenant_data: object, tenant_ref: str) -> dict:
    if not isinstance(tenant_data, dict):
        raise RuntimeError(f"Variables for tenant {tenant_ref!r} must be a mapping.")
    variables = tenant_data.get("variables")
    if variables is not None:
        if not isinstance(variables, dict):
            raise RuntimeError(f"Variables for tenant {tenant_ref!r} must be a mapping.")
        return variables

    # Read the previous local-demo format while users migrate their ignored
    # secrets.yml. SMTP host/port are ordinary configuration; other old entries
    # retain the old secret-by-default behavior.
    legacy = tenant_data.get("secrets", tenant_data)
    if not isinstance(legacy, dict):
        raise RuntimeError(f"Secrets for tenant {tenant_ref!r} must be a mapping.")
    return {
        name: {
            "value": value,
            "sensitive": str(name).upper() not in {"SMTP_HOST", "SMTP_PORT"},
        }
        for name, value in legacy.items()
    }


def _vault_configuration_path(tenant_id: str, variable_id: str) -> str:
    logical = f"{PREFIX}/tenants/{tenant_id}/secrets/configuration-variable/{variable_id}"
    return f"{parse.quote(MOUNT, safe='')}/data/{parse.quote(logical, safe='/')}"


def seed() -> tuple[int, int]:
    if not SECRETS.exists():
        print("vault-seed: no local seed file found; skipping demo secret seeding.", flush=True)
        return 0, 0
    payload = yaml.safe_load(SECRETS.read_text(encoding="utf-8")) or {}
    tenants = payload.get("tenants", {}) if isinstance(payload, dict) else {}
    if not isinstance(tenants, dict):
        raise RuntimeError("The demo secrets file must contain a tenants mapping.")
    seed_token_file = STATE / "seed-token"
    if not seed_token_file.exists():
        raise RuntimeError("Scoped Vault demo-seed credential is missing; run vault-demo first.")
    seed_token = seed_token_file.read_text(encoding="utf-8").strip()
    if not seed_token:
        raise RuntimeError("Scoped Vault demo-seed credential is empty; rerun vault-demo.")
    wait_for_backend_health()
    tenant_id = tenant_id_from_database()
    if tenant_id != DEMO_TENANT_ID:
        raise RuntimeError(
            "The local demo-seed token is scoped to the configured demo tenant ID; "
            "update M8FLOW_VAULT_DEMO_TENANT_ID and rerun vault-demo."
        )
    written = skipped = 0
    for tenant_ref, tenant_data in tenants.items():
        if str(tenant_ref) not in {"m8flow", os.getenv("M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS", "m8flow")}:
            raise RuntimeError("Local demo seeding currently supports only the default m8flow tenant alias.")
        variables = _variables_for_tenant(tenant_data, str(tenant_ref))
        for raw_name, definition in variables.items():
            name = str(raw_name).strip()
            if not NAME_PATTERN.fullmatch(name):
                raise RuntimeError(f"Invalid demo variable name for tenant {tenant_ref!r}.")
            if not isinstance(definition, dict) or "value" not in definition:
                raise RuntimeError(f"Demo variable {name!r} must define value and sensitivity.")
            value = definition["value"]
            sensitive = definition.get("sensitive")
            description = definition.get("description")
            if not isinstance(sensitive, bool):
                raise RuntimeError(f"Demo variable {name!r} must set sensitive to true or false.")
            if description is not None and not isinstance(description, str):
                raise RuntimeError(f"Demo variable {name!r} description must be a string.")
            if not isinstance(value, (str, int, float, bool)) or value == "":
                raise RuntimeError(f"Demo variable {name!r} must have a non-empty scalar value.")
            if sensitive and not isinstance(value, str):
                raise RuntimeError(f"Sensitive demo variable {name!r} must have a string value.")

            with psycopg.connect(
                os.environ["M8FLOW_BACKEND_DATABASE_URI"].replace(
                    "postgresql+psycopg://", "postgresql://", 1
                ),
                connect_timeout=10,
            ) as conn:
                conn.execute("SELECT set_config('app.current_tenant', %s, true)", (tenant_id,))
                existing = conn.execute(
                    "SELECT id, is_sensitive FROM m8flow_named_value "
                    "WHERE m8f_tenant_id = %s AND lower(name) = lower(%s) FOR UPDATE",
                    (tenant_id, name),
                ).fetchone()
                if existing and not OVERWRITE:
                    skipped += 1
                    continue

                variable_id = str(existing[0]) if existing else str(uuid.uuid4())
                provider_key = variable_id if sensitive else None
                if sensitive:
                    path = _vault_configuration_path(tenant_id, variable_id)
                    status, _ = vault_call("GET", path, seed_token, expected=(200, 404))
                    if status == 200 and not OVERWRITE and not existing:
                        skipped += 1
                        continue
                    vault_call("POST", path, seed_token, {"data": {"value": value}})

                if existing:
                    conn.execute(
                        "UPDATE m8flow_named_value SET name = %s, description = %s, "
                        "is_sensitive = %s, value = %s, is_configured = true, "
                        "provider_key = %s, updated_at = now() WHERE id = %s "
                        "AND m8f_tenant_id = %s",
                        (
                            name, description, sensitive, None if sensitive else Json(value),
                            provider_key, variable_id, tenant_id,
                        ),
                    )
                else:
                    conn.execute(
                        "INSERT INTO m8flow_named_value "
                        "(id, m8f_tenant_id, name, description, is_sensitive, value, "
                        "is_configured, provider_key, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, true, %s, now(), now())",
                        (
                            variable_id, tenant_id, name, description, sensitive,
                            None if sensitive else Json(value), provider_key,
                        ),
                    )
            written += 1
    print(f"vault-seed: seeded {written} named configuration variable(s); preserved {skipped} existing variable(s).", flush=True)
    return written, skipped


if __name__ == "__main__":
    try:
        seed()
    except Exception as exc:
        raise SystemExit(f"vault-seed: failed: {exc}")
