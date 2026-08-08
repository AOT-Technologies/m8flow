#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib import error, request
import uuid

import sqlalchemy as sa
import yaml

from demo_identity import DemoTenantIdentity, wait_for_demo_tenant_identity


BACKEND_STATUS_URL = os.getenv("M8FLOW_VAULT_DEMO_BACKEND_STATUS_URL") or "http://m8flow-backend:6840/v1.0/status"
WAIT_TIMEOUT_SECONDS = float(os.getenv("M8FLOW_VAULT_DEMO_WAIT_TIMEOUT_SECONDS") or "180")
WAIT_INTERVAL_SECONDS = float(os.getenv("M8FLOW_VAULT_DEMO_WAIT_INTERVAL_SECONDS") or "2")
STATE_DIR = Path(os.getenv("M8FLOW_VAULT_DEMO_STATE_DIR") or "/vault/demo")
RUNTIME_ENV_FILE = STATE_DIR / "runtime.env"
VERIFICATION_FILE = STATE_DIR / "verification.json"
SECRETS_FILE = Path(os.getenv("M8FLOW_VAULT_DEMO_SECRETS_FILE") or "/app/docker/vault/demo/secrets.yml")


@dataclass(frozen=True)
class SeededSecret:
    tenant_reference: str
    secret_name: str
    value: str


def log(message: str) -> None:
    print(f"vault-demo-seed: {message}", flush=True)


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


def wait_for_backend_status() -> dict[str, Any]:
    deadline = time.time() + WAIT_TIMEOUT_SECONDS
    last_error: str | None = None

    while time.time() < deadline:
        req = request.Request(BACKEND_STATUS_URL, method="GET")
        try:
            with request.urlopen(req, timeout=10) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            last_error = f"{exc.code} from {BACKEND_STATUS_URL}"
            time.sleep(WAIT_INTERVAL_SECONDS)
            continue
        except error.URLError as exc:
            last_error = str(exc)
            time.sleep(WAIT_INTERVAL_SECONDS)
            continue

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}

        if isinstance(payload, dict):
            return payload

        last_error = "backend status returned a non-JSON response"
        time.sleep(WAIT_INTERVAL_SECONDS)

    fail(
        f"Timed out waiting for backend status at {BACKEND_STATUS_URL}. "
        f"Last error: {last_error or 'unknown error'}"
    )


def load_seeded_secrets() -> list[SeededSecret]:
    if not SECRETS_FILE.exists():
        fail(f"Vault demo secrets file is missing: {SECRETS_FILE}")

    raw_payload = yaml.safe_load(SECRETS_FILE.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_payload, dict):
        fail(f"Vault demo secrets file must contain a top-level mapping: {SECRETS_FILE}")

    tenants = raw_payload.get("tenants")
    if not isinstance(tenants, dict) or not tenants:
        fail(f"Vault demo secrets file must define at least one tenant under 'tenants': {SECRETS_FILE}")

    seeded_secrets: list[SeededSecret] = []
    for tenant_id, tenant_payload in tenants.items():
        normalized_tenant_reference = str(tenant_id).strip()
        if not normalized_tenant_reference or "/" in normalized_tenant_reference:
            fail(f"Invalid tenant id in {SECRETS_FILE}: {tenant_id!r}")

        if isinstance(tenant_payload, dict) and "secrets" in tenant_payload:
            secrets_payload = tenant_payload.get("secrets")
        else:
            secrets_payload = tenant_payload

        if not isinstance(secrets_payload, dict) or not secrets_payload:
            fail(f"Tenant '{normalized_tenant_reference}' must define at least one secret in {SECRETS_FILE}.")

        for secret_name, secret_value in secrets_payload.items():
            normalized_secret_name = str(secret_name).strip()
            if not normalized_secret_name or "/" in normalized_secret_name:
                fail(
                    f"Invalid secret name for tenant '{normalized_tenant_reference}' in {SECRETS_FILE}: {secret_name!r}"
                )
            seeded_secrets.append(
                SeededSecret(
                    tenant_reference=normalized_tenant_reference,
                    secret_name=normalized_secret_name,
                    value=str(secret_value),
                )
            )

    return seeded_secrets


def database_uri() -> str:
    value = os.getenv("M8FLOW_BACKEND_DATABASE_URI") or os.getenv("SPIFFWORKFLOW_BACKEND_DATABASE_URI")
    if not value or not value.strip():
        fail("Vault demo metadata seeding requires M8FLOW_BACKEND_DATABASE_URI or SPIFFWORKFLOW_BACKEND_DATABASE_URI.")
    return value.strip()


def realm_from_service(service: Any) -> str | None:
    if not isinstance(service, str):
        return None
    normalized = service.strip().rstrip("/")
    if "/realms/" not in normalized:
        return None
    return normalized.rsplit("/realms/", 1)[-1] or None


def reflect_tables(engine: sa.Engine) -> tuple[sa.Table, sa.Table, sa.Table, sa.Table]:
    metadata = sa.MetaData()
    tenant_table = sa.Table("m8flow_tenant", metadata, autoload_with=engine)
    user_table = sa.Table("user", metadata, autoload_with=engine)
    principal_table = sa.Table("principal", metadata, autoload_with=engine)
    vault_metadata_table = sa.Table("vault_metadata", metadata, autoload_with=engine)
    return tenant_table, user_table, principal_table, vault_metadata_table


def resolve_current_tenant_id(
    connection: sa.Connection,
    tenant_table: sa.Table,
    identity: DemoTenantIdentity,
    tenant_reference: str,
) -> str:
    if tenant_reference == identity.organization_alias:
        tenant_row = connection.execute(
            sa.select(
                tenant_table.c.id,
                tenant_table.c.slug,
            ).where(
                sa.or_(
                    tenant_table.c.id == identity.organization_id,
                    tenant_table.c.slug == identity.organization_alias,
                )
            )
        ).mappings().first()
        if tenant_row is None:
            fail(
                f"Could not resolve tenant reference '{tenant_reference}' in m8flow_tenant "
                f"after backend startup."
            )
        resolved_tenant_id = str(tenant_row["id"]).strip()
        if resolved_tenant_id != identity.organization_id:
            fail(
                f"Tenant reference '{tenant_reference}' resolved to '{resolved_tenant_id}', "
                f"but Keycloak organization id is '{identity.organization_id}'."
            )
        return resolved_tenant_id

    tenant_row = connection.execute(
        sa.select(tenant_table.c.id).where(
            sa.or_(
                tenant_table.c.id == tenant_reference,
                tenant_table.c.slug == tenant_reference,
            )
        )
    ).mappings().first()
    if tenant_row is None:
        fail(f"Could not resolve tenant reference '{tenant_reference}' in m8flow_tenant.")
    return str(tenant_row["id"]).strip()


def ensure_local_admin_user(
    connection: sa.Connection,
    user_table: sa.Table,
    principal_table: sa.Table,
    identity: DemoTenantIdentity,
) -> int:
    now = int(time.time())

    exact_user = connection.execute(
        sa.select(
            user_table.c.id,
            user_table.c.username,
            user_table.c.service,
            user_table.c.service_id,
            user_table.c.email,
            user_table.c.display_name,
        ).where(
            sa.and_(
                user_table.c.service == identity.admin_service,
                user_table.c.service_id == identity.admin_service_id,
            )
        )
    ).mappings().first()

    target_user_id: int
    if exact_user is not None:
        target_user_id = int(exact_user["id"])
        user_updates: dict[str, Any] = {}
        if exact_user["username"] != identity.admin_username:
            user_updates["username"] = identity.admin_username
        if exact_user["email"] != identity.admin_email:
            user_updates["email"] = identity.admin_email
        if exact_user["display_name"] != identity.admin_username:
            user_updates["display_name"] = identity.admin_username
        if user_updates:
            user_updates["updated_at_in_seconds"] = now
            connection.execute(
                sa.update(user_table).where(user_table.c.id == target_user_id).values(**user_updates)
            )
    else:
        same_username = connection.execute(
            sa.select(
                user_table.c.id,
                user_table.c.service,
                user_table.c.service_id,
            ).where(user_table.c.username == identity.admin_username)
        ).mappings().first()

        if same_username is not None:
            existing_service = str(same_username["service"]).strip()
            if (
                existing_service != identity.admin_service
                and realm_from_service(existing_service) != realm_from_service(identity.admin_service)
            ):
                fail(
                    f"Cannot seed local metadata for username '{identity.admin_username}' because it is already "
                    f"bound to a different issuer '{existing_service}'."
                )
            target_user_id = int(same_username["id"])
            connection.execute(
                sa.update(user_table)
                .where(user_table.c.id == target_user_id)
                .values(
                    service=identity.admin_service,
                    service_id=identity.admin_service_id,
                    email=identity.admin_email,
                    display_name=identity.admin_username,
                    updated_at_in_seconds=now,
                )
            )
        else:
            target_user_id = int(
                connection.execute(
                    sa.insert(user_table)
                    .values(
                        username=identity.admin_username,
                        email=identity.admin_email,
                        service=identity.admin_service,
                        service_id=identity.admin_service_id,
                        display_name=identity.admin_username,
                        created_at_in_seconds=now,
                        updated_at_in_seconds=now,
                    )
                    .returning(user_table.c.id)
                ).scalar_one()
            )

    principal_exists = connection.execute(
        sa.select(principal_table.c.id).where(principal_table.c.user_id == target_user_id)
    ).scalar_one_or_none()
    if principal_exists is None:
        connection.execute(sa.insert(principal_table).values(user_id=target_user_id))

    return target_user_id


def seed_vault_metadata(
    connection: sa.Connection,
    vault_metadata_table: sa.Table,
    *,
    tenant_id: str,
    admin_user_id: int,
    admin_username: str,
    secrets: list[SeededSecret],
) -> tuple[int, int, int]:
    inserted = 0
    updated = 0
    unchanged = 0
    now = int(time.time())

    for secret in secrets:
        existing_row = connection.execute(
            sa.select(
                vault_metadata_table.c.id,
                vault_metadata_table.c.user_id,
                vault_metadata_table.c.created_by,
                vault_metadata_table.c.modified_by,
            ).where(
                sa.and_(
                    vault_metadata_table.c.m8f_tenant_id == tenant_id,
                    vault_metadata_table.c.name == secret.secret_name,
                )
            )
        ).mappings().first()

        if existing_row is None:
            connection.execute(
                sa.insert(vault_metadata_table).values(
                    id=uuid.uuid4().hex,
                    name=secret.secret_name,
                    user_id=admin_user_id,
                    created_by=admin_username,
                    modified_by=admin_username,
                    created_at_in_seconds=now,
                    updated_at_in_seconds=now,
                    m8f_tenant_id=tenant_id,
                )
            )
            inserted += 1
            continue

        row_updates: dict[str, Any] = {}
        if int(existing_row["user_id"]) != admin_user_id:
            row_updates["user_id"] = admin_user_id
        if existing_row["created_by"] != admin_username:
            row_updates["created_by"] = admin_username
        if existing_row["modified_by"] != admin_username:
            row_updates["modified_by"] = admin_username

        if row_updates:
            row_updates["updated_at_in_seconds"] = now
            connection.execute(
                sa.update(vault_metadata_table)
                .where(vault_metadata_table.c.id == existing_row["id"])
                .values(**row_updates)
            )
            updated += 1
        else:
            unchanged += 1

    return inserted, updated, unchanged


def verify_backend_wrapper(secret_name: str, expected_value: str, tenant_id: str) -> None:
    load_env_file(RUNTIME_ENV_FILE)

    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    backend_src = repo_root / "m8flow-backend" / "src"
    backend_src_str = str(backend_src)
    if backend_src_str not in sys.path:
        sys.path.insert(0, backend_src_str)

    from m8flow_backend.services.vault_client import VaultClient, VaultSettings

    client = VaultClient(settings=VaultSettings.from_env())
    if not client.check_availability():
        fail("Vault client wrapper reported Vault unavailable during metadata seeding.")

    logical_path = f"tenants/{tenant_id}/secrets/{secret_name}"
    resolved_value = client.retrieve_secret(logical_path)
    if resolved_value != expected_value:
        fail(
            f"Vault client wrapper read '{logical_path}', but the resolved value "
            "did not match the seeded demo secret."
        )


def write_verification_report(report: dict[str, Any]) -> None:
    existing: dict[str, Any] = {}
    if VERIFICATION_FILE.exists():
        try:
            loaded = json.loads(VERIFICATION_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except json.JSONDecodeError:
            existing = {}

    existing.update(report)
    VERIFICATION_FILE.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        wait_for_backend_status()
        identity = wait_for_demo_tenant_identity(
            timeout_seconds=WAIT_TIMEOUT_SECONDS,
            interval_seconds=WAIT_INTERVAL_SECONDS,
        )
        seeded_secrets = load_seeded_secrets()
        if not seeded_secrets:
            fail("Vault demo metadata seeding requires at least one seeded secret.")

        engine = sa.create_engine(database_uri())
        tenant_id: str | None = None
        admin_user_id: int | None = None
        inserted = 0
        updated = 0
        unchanged = 0

        with engine.begin() as connection:
            tenant_table, user_table, principal_table, vault_metadata_table = reflect_tables(engine)
            admin_user_id = ensure_local_admin_user(connection, user_table, principal_table, identity)

            tenant_reference_groups: dict[str, list[SeededSecret]] = {}
            for secret in seeded_secrets:
                tenant_reference_groups.setdefault(secret.tenant_reference, []).append(secret)

            for tenant_reference, tenant_secrets in tenant_reference_groups.items():
                current_tenant_id = resolve_current_tenant_id(connection, tenant_table, identity, tenant_reference)
                if tenant_id is None:
                    tenant_id = current_tenant_id
                elif tenant_id != current_tenant_id:
                    fail(
                        "Vault demo metadata seeding expected one current tenant id for the configured seed data, "
                        f"but found both '{tenant_id}' and '{current_tenant_id}'."
                    )
                group_inserted, group_updated, group_unchanged = seed_vault_metadata(
                    connection,
                    vault_metadata_table,
                    tenant_id=current_tenant_id,
                    admin_user_id=admin_user_id,
                    admin_username=identity.admin_username,
                    secrets=tenant_secrets,
                )
                inserted += group_inserted
                updated += group_updated
                unchanged += group_unchanged

        if tenant_id is None or admin_user_id is None:
            fail("Vault demo metadata seeding did not resolve a target tenant or admin user.")

        first_secret = seeded_secrets[0]
        verify_backend_wrapper(first_secret.secret_name, first_secret.value, tenant_id)
        write_verification_report(
            {
                "metadata_admin_user_id": admin_user_id,
                "metadata_admin_username": identity.admin_username,
                "metadata_inserted": inserted,
                "metadata_seeded_count": inserted + updated + unchanged,
                "metadata_tenant_id": tenant_id,
                "metadata_unchanged": unchanged,
                "metadata_updated": updated,
            }
        )
        log(
            "Metadata seeding complete "
            f"(tenant_id={tenant_id}, admin_user_id={admin_user_id}, "
            f"inserted={inserted}, updated={updated}, unchanged={unchanged})."
        )
        return 0
    except Exception as exc:
        print(f"vault-demo-seed: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
