#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from demo_identity import wait_for_demo_tenant_identity
from seeded_secrets import load_seeded_secret_specs

WAIT_TIMEOUT_SECONDS = float(os.getenv("M8FLOW_VAULT_DEMO_WAIT_TIMEOUT_SECONDS") or "180")
WAIT_INTERVAL_SECONDS = float(os.getenv("M8FLOW_VAULT_DEMO_WAIT_INTERVAL_SECONDS") or "2")


def fail(message: str) -> None:
    raise RuntimeError(message)


def format_missing_secrets_file_message(path: Path) -> str:
    message = f"Vault demo secrets file is missing: {path}"
    if path.name == "secrets.yml":
        message += ". Copy docker/vault/demo/secrets.yml.sample to docker/vault/demo/secrets.yml first."
    return message


def load_env_file(path: Path) -> None:
    if not path.exists():
        fail(f"Vault demo runtime env file is missing: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


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
        identity = wait_for_demo_tenant_identity(
            timeout_seconds=WAIT_TIMEOUT_SECONDS,
            interval_seconds=WAIT_INTERVAL_SECONDS,
        )
        seeded_secret = load_seeded_secret_specs(
            secrets_file,
            organization_alias=identity.organization_alias,
            organization_id=identity.organization_id,
            missing_file_message_factory=format_missing_secrets_file_message,
        )[0]

        from m8flow_backend.services.tenant_scoped_vault_client_provider import TenantScopedVaultClientProvider
        from m8flow_backend.services.tenant_vault_provisioning_service import TenantVaultProvisioningService
        from m8flow_backend.services.vault_client import VaultClient, VaultClientError, VaultSettings

        broker_client = VaultClient(settings=VaultSettings.from_env())
        if not broker_client.check_availability():
            fail("Vault client wrapper reported Vault unavailable.")

        logical_path = f"tenants/{seeded_secret.tenant_id}/secrets/{seeded_secret.secret_name}"
        provisioned_identity = TenantVaultProvisioningService(vault_client=broker_client).provision_tenant_identity(
            seeded_secret.tenant_id
        )

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
                    f"Broker Vault identity still has direct read access to '{logical_path}'. "
                    "The local demo should only read tenant secrets through a tenant-scoped Vault client."
                )

        client = TenantScopedVaultClientProvider(broker_vault_client=broker_client).for_tenant(
            seeded_secret.tenant_id
        )
        resolved_value = client.vault_client.retrieve_secret(logical_path)
        if resolved_value != seeded_secret.value:
            fail(
                f"Vault client wrapper read '{logical_path}', but the resolved value "
                "did not match the seeded demo secret."
            )

        print(
            json.dumps(
                {
                    "admin_username": identity.admin_username,
                    "broker_direct_read_blocked": broker_direct_read_blocked,
                    "verified": True,
                    "mount_point": client.vault_client.settings.mount_point,
                    "path_prefix": client.vault_client.settings.secret_path_prefix,
                    "secret_path": logical_path,
                    "tenant_policy_name": provisioned_identity.policy_name,
                    "tenant_role_name": provisioned_identity.role_name,
                    "tenant_id": seeded_secret.tenant_id,
                }
            )
        )
        return 0
    except Exception as exc:
        print(f"vault-demo-verify: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
