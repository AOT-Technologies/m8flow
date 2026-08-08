#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa
import yaml

from demo_identity import wait_for_demo_tenant_identity

WAIT_TIMEOUT_SECONDS = float(os.getenv("M8FLOW_VAULT_DEMO_WAIT_TIMEOUT_SECONDS") or "180")
WAIT_INTERVAL_SECONDS = float(os.getenv("M8FLOW_VAULT_DEMO_WAIT_INTERVAL_SECONDS") or "2")


def fail(message: str) -> None:
    raise RuntimeError(message)


def load_env_file(path: Path) -> None:
    if not path.exists():
        fail(f"Vault demo runtime env file is missing: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def load_first_seeded_secret(path: Path) -> tuple[str, str, str]:
    if not path.exists():
        fail(f"Vault demo secrets file is missing: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tenants = payload.get("tenants")
    if not isinstance(tenants, dict) or not tenants:
        fail(f"Vault demo secrets file must define at least one tenant: {path}")

    first_tenant_id, first_tenant_payload = next(iter(tenants.items()))
    if isinstance(first_tenant_payload, dict) and "secrets" in first_tenant_payload:
        secrets_payload = first_tenant_payload.get("secrets")
    else:
        secrets_payload = first_tenant_payload
    if not isinstance(secrets_payload, dict) or not secrets_payload:
        fail(f"Vault demo tenant '{first_tenant_id}' must define at least one secret.")

    first_secret_name, first_secret_value = next(iter(secrets_payload.items()))
    return str(first_tenant_id), str(first_secret_name), str(first_secret_value)


def database_uri() -> str:
    value = os.getenv("M8FLOW_BACKEND_DATABASE_URI") or os.getenv("SPIFFWORKFLOW_BACKEND_DATABASE_URI")
    if not value or not value.strip():
        fail("Vault demo verification requires M8FLOW_BACKEND_DATABASE_URI or SPIFFWORKFLOW_BACKEND_DATABASE_URI.")
    return value.strip()


def resolve_current_tenant_id(tenant_reference: str, organization_alias: str, organization_id: str) -> str:
    engine = sa.create_engine(database_uri())
    metadata = sa.MetaData()
    tenant_table = sa.Table("m8flow_tenant", metadata, autoload_with=engine)

    with engine.connect() as connection:
        tenant_row = connection.execute(
            sa.select(tenant_table.c.id).where(
                sa.or_(
                    tenant_table.c.id == tenant_reference,
                    tenant_table.c.slug == tenant_reference,
                )
            )
        ).mappings().first()

    if tenant_row is None:
        fail(f"Vault demo verification could not resolve tenant reference '{tenant_reference}' in m8flow_tenant.")

    resolved_tenant_id = str(tenant_row["id"]).strip()
    if tenant_reference == organization_alias and resolved_tenant_id != organization_id:
        fail(
            f"Vault demo verification resolved tenant reference '{tenant_reference}' to '{resolved_tenant_id}', "
            f"but Keycloak organization id is '{organization_id}'."
        )
    return resolved_tenant_id


def verify_vault_metadata(tenant_id: str, secret_name: str, admin_username: str) -> None:
    engine = sa.create_engine(database_uri())
    metadata = sa.MetaData()
    user_table = sa.Table("user", metadata, autoload_with=engine)
    vault_metadata_table = sa.Table("vault_metadata", metadata, autoload_with=engine)

    with engine.connect() as connection:
        metadata_row = connection.execute(
            sa.select(
                vault_metadata_table.c.id,
                user_table.c.username,
                vault_metadata_table.c.user_id,
                vault_metadata_table.c.m8f_tenant_id,
            )
            .select_from(vault_metadata_table.join(user_table, vault_metadata_table.c.user_id == user_table.c.id))
            .where(
                sa.and_(
                    vault_metadata_table.c.m8f_tenant_id == tenant_id,
                    vault_metadata_table.c.name == secret_name,
                )
            )
        ).mappings().first()

    if metadata_row is None:
        fail(
            f"Vault demo verification could not find vault_metadata for tenant '{tenant_id}' and secret '{secret_name}'."
        )
    if metadata_row["username"] != admin_username:
        fail(
            f"Vault demo verification expected vault_metadata for secret '{secret_name}' to belong to "
            f"'{admin_username}', but found '{metadata_row['username']}'."
        )


def main() -> int:
    try:
        script_path = Path(__file__).resolve()
        repo_root = script_path.parents[3]
        backend_src = repo_root / "m8flow-backend" / "src"
        backend_src_str = str(backend_src)
        if backend_src_str not in sys.path:
            sys.path.insert(0, backend_src_str)

        runtime_env = Path(os.getenv("M8FLOW_VAULT_DEMO_ENV_FILE") or "/vault/demo/runtime.env")
        secrets_file = Path(
            os.getenv("M8FLOW_VAULT_DEMO_SECRETS_FILE") or str(script_path.with_name("secrets.yml"))
        )
        load_env_file(runtime_env)
        tenant_reference, secret_name, expected_value = load_first_seeded_secret(secrets_file)
        identity = wait_for_demo_tenant_identity(
            timeout_seconds=WAIT_TIMEOUT_SECONDS,
            interval_seconds=WAIT_INTERVAL_SECONDS,
        )
        tenant_id = resolve_current_tenant_id(
            tenant_reference,
            organization_alias=identity.organization_alias,
            organization_id=identity.organization_id,
        )

        from m8flow_backend.services.vault_client import VaultClient, VaultSettings

        client = VaultClient(settings=VaultSettings.from_env())
        if not client.check_availability():
            fail("Vault client wrapper reported Vault unavailable.")

        logical_path = f"tenants/{tenant_id}/secrets/{secret_name}"
        resolved_value = client.retrieve_secret(logical_path)
        if resolved_value != expected_value:
            fail(
                f"Vault client wrapper read '{logical_path}', but the resolved value "
                "did not match the seeded demo secret."
            )
        verify_vault_metadata(tenant_id, secret_name, identity.admin_username)

        print(
            json.dumps(
                {
                    "admin_username": identity.admin_username,
                    "metadata_verified": True,
                    "verified": True,
                    "mount_point": client.settings.mount_point,
                    "path_prefix": client.settings.secret_path_prefix,
                    "secret_path": logical_path,
                }
            )
        )
        return 0
    except Exception as exc:
        print(f"vault-demo-verify: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
