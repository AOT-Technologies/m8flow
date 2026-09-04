#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from demo_identity import ensure_backend_src_on_path
from seeded_secrets import load_seeded_secret_specs
from seed_named_values import _flask_app_from_wrapped_application

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


def format_failure_message(_exc: Exception) -> str:
    return "vault-demo-verify failed."


def main() -> int:
    try:
        script_path = Path(__file__).resolve()
        ensure_backend_src_on_path()

        runtime_env = Path(os.getenv("M8FLOW_VAULT_DEMO_ENV_FILE") or "/vault/demo/runtime.env")
        secrets_file = Path(
            os.getenv("M8FLOW_VAULT_DEMO_SECRETS_FILE") or str(script_path.with_name("secrets.yml"))
        )
        load_env_file(runtime_env)
        from flask import g
        from m8flow_backend.app import app
        from m8flow_backend.config import default_organization_alias
        from m8flow_backend.models.named_value import NamedValueModel
        from m8flow_backend.services.named_value_secret_storage import (
            VaultNamedValueSecretStorage,
            vault_provider_key,
        )
        from m8flow_backend.startup.shared_realm_bootstrap import (
            resolve_default_shared_realm_tenant_id,
        )

        flask_app = _flask_app_from_wrapped_application(app)
        with flask_app.app_context(), flask_app.test_request_context("/"):
            tenant_id = resolve_default_shared_realm_tenant_id()
            if not tenant_id:
                fail("The canonical demo tenant is unavailable in the database.")
            tenant_alias = default_organization_alias()
            seeded_secrets = load_seeded_secret_specs(
                secrets_file,
                organization_alias=tenant_alias,
                organization_id=tenant_id,
                missing_file_message_factory=format_missing_secrets_file_message,
            )
            g.m8flow_tenant_id = tenant_id
            rows = NamedValueModel.query.filter_by(m8f_tenant_id=tenant_id).all()
            rows_by_name = {row.name.casefold(): row for row in rows}
            if not seeded_secrets:
                if rows:
                    fail("An empty demo secrets file created configuration-variable catalog rows.")
            else:
                if len(rows_by_name) != len(seeded_secrets):
                    fail("The configuration-variable catalog does not match the demo seed file.")
                storage = VaultNamedValueSecretStorage()
                for spec in seeded_secrets:
                    row = rows_by_name.get(spec.secret_name.casefold())
                    if (
                        row is None
                        or not row.is_sensitive
                        or not row.is_configured
                        or row.value is not None
                    ):
                        fail("A seeded configuration-variable catalog row is invalid.")
                    if vault_provider_key(row.m8f_tenant_id, row.id).split("/")[3] != "configuration-variable":
                        fail("A seeded configuration-variable used a noncanonical Vault path.")
                    document = storage.read_document(row)
                    if (
                        not isinstance(document, dict)
                        or set(document) != {"value"}
                        or document.get("value") != spec.value
                    ):
                        fail("A seeded Vault document is missing or does not use the value-only format.")

        print("vault-demo-verify: Verification succeeded.", flush=True)
        return 0
    except Exception as exc:
        print(format_failure_message(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
