"""Seed demo manual configuration variables after backend migrations complete."""

from __future__ import annotations

import os
import base64
import json
import math
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from demo_identity import ensure_backend_src_on_path
from seeded_secrets import SeededSecretSpec, load_seeded_secret_specs


@dataclass
class SeedResult:
    created: int = 0
    reused: int = 0
    updated: int = 0


def _positive_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive number.") from exc
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name} must be a positive number.")
    return value


def wait_for_backend_ready() -> None:
    """Wait until the backend has completed its migrations and startup hooks."""
    base_url = (os.getenv("M8FLOW_VAULT_DEMO_BACKEND_URL") or "http://m8flow-backend:6840").rstrip("/")
    timeout_seconds = _positive_float_env("M8FLOW_VAULT_DEMO_SEED_WAIT_TIMEOUT_SECONDS", 180.0)
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        try:
            with request.urlopen(f"{base_url}/v1.0/status", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and isinstance(payload, dict) and payload.get("ok") is True:
                return
        except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(2)

    raise RuntimeError("Backend did not become ready before the demo seed timeout.")


def verify_authenticated_list_api(secrets: list[SeededSecretSpec], tenant_id: str) -> None:
    """Prove the browser-facing metadata API can see the rows without values."""
    enabled = os.getenv("M8FLOW_VAULT_DEMO_VERIFY_LIST_API", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return

    keycloak_url = (
        os.getenv("M8FLOW_VAULT_DEMO_KEYCLOAK_URL") or "http://keycloak-proxy:6842"
    ).rstrip("/")
    realm = os.getenv("M8FLOW_KEYCLOAK_SHARED_REALM", "m8flow")
    client_id = os.getenv("M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID", "m8flow-backend")
    client_secret = os.getenv(
        "M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET", "f041b49ae7f1a35daa10917459814bcd"
    )
    username = os.getenv("KEYCLOAK_ADMIN_USER", "admin")
    password = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin")
    token_body = (
        f"grant_type=password&username={parse.quote(username, safe='')}&"
        f"password={parse.quote(password, safe='')}&client_id={parse.quote(client_id, safe='')}"
    ).encode("utf-8")
    basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    try:
        token_request = request.Request(
            f"{keycloak_url}/realms/{parse.quote(realm, safe='')}/protocol/openid-connect/token",
            data=token_body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic_auth}",
            },
        )
        with request.urlopen(token_request, timeout=15) as response:
            access_token = json.loads(response.read().decode("utf-8")).get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Local Keycloak did not issue an access token.")
        backend_url = (
            os.getenv("M8FLOW_VAULT_DEMO_BACKEND_URL") or "http://m8flow-backend:6840"
        ).rstrip("/")
        list_request = request.Request(
            f"{backend_url}/v1.0/m8flow/named-values",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with request.urlopen(list_request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("The authenticated configuration-variable list API is unavailable.") from exc

    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        raise RuntimeError("The authenticated configuration-variable list API returned an invalid response.")
    rows_by_name = {
        row.get("name", "").casefold(): row for row in values if isinstance(row, dict)
    }
    for secret in secrets:
        row = rows_by_name.get(secret.secret_name.casefold())
        if (
            not isinstance(row, dict)
            or row.get("tenantId") != tenant_id
            or row.get("isSensitive") is not True
            or row.get("isConfigured") is not True
            or row.get("value") is not None
        ):
            raise RuntimeError("The authenticated configuration-variable list API did not return safe seeded metadata.")


def reconcile_seeded_values(
    secrets: list[SeededSecretSpec],
    *,
    user_id: int | None,
    overwrite: bool,
    named_value_service: Any,
) -> SeedResult:
    """Reconcile the demo file through the same catalog and storage service as the UI."""
    result = SeedResult()
    values_by_tenant: dict[str, dict[str, Any]] = {}

    for secret in secrets:
        values = values_by_tenant.setdefault(
            secret.tenant_id,
            {
                value.name.casefold(): value
                for value in named_value_service.list_values(secret.tenant_id)
            },
        )
        normalized_name = named_value_service._normalized_name(secret.secret_name)
        existing = values.get(normalized_name.casefold())

        if existing is None:
            row = named_value_service.create_value(
                secret.tenant_id,
                user_id,
                normalized_name,
                secret.value,
                "Seeded for local Vault development.",
                is_sensitive=True,
                # The shared-realm local user is created lazily on first login.
                # Demo bootstrap must seed before any human login, so use the
                # nullable system-seed actor supported by the catalog schema.
                allow_unattributed_sensitive=True,
            )
            values[normalized_name.casefold()] = row
            result.created += 1
            continue

        # Never overwrite a value-only Vault document merely because the demo
        # profile runs again. Explicit overwrite is the sole replacement path.
        if existing.is_sensitive and not overwrite:
            result.reused += 1
            continue

        named_value_service.update_value(
            existing,
            name=existing.name,
            value=secret.value,
            description=existing.description,
            is_sensitive=True,
        )
        result.updated += 1

    return result


def verify_seeded_values(
    secrets: list[SeededSecretSpec], *, named_value_service: Any, storage: Any | None = None
) -> None:
    """Confirm catalog rows and provider payloads exist without logging values."""
    if storage is None:
        from m8flow_backend.services.named_value_secret_storage import (
            VaultNamedValueSecretStorage,
            get_named_value_secret_storage,
        )

        storage = get_named_value_secret_storage()
        if not isinstance(storage, VaultNamedValueSecretStorage):
            raise RuntimeError("Seeded configuration variables require Vault storage.")
    values_by_tenant: dict[str, dict[str, Any]] = {}
    for secret in secrets:
        values = values_by_tenant.setdefault(
            secret.tenant_id,
            {
                value.name.casefold(): value
                for value in named_value_service.list_values(secret.tenant_id)
            },
        )
        row = values.get(secret.secret_name.casefold())
        if row is None or not row.is_sensitive or not row.is_configured or row.value is not None:
            raise RuntimeError("Seeded configuration-variable catalog verification failed.")
        # Use the tenant-scoped provider, then validate the exact minimal
        # document shape without emitting its plaintext value anywhere.
        document = storage.read_document(row)
        if (
            not isinstance(document, dict)
            or set(document) != {"value"}
            or not isinstance(document.get("value"), str)
        ):
            raise RuntimeError("Seeded configuration-variable Vault verification failed.")


def _flask_app_from_wrapped_application(application):
    """Unwrap the ASGI/Connexion layers used by the backend factory."""
    current = application
    for _ in range(4):
        if callable(getattr(current, "app_context", None)):
            return current
        current = getattr(current, "app", None)
        if current is None:
            break
    raise RuntimeError("Could not access the backend Flask application for demo seeding.")


def main() -> int:
    ensure_backend_src_on_path()
    from flask import g
    from m8flow_backend.app import app
    from m8flow_backend.config import default_organization_alias
    from m8flow_backend.services.named_value_service import NamedValueService
    from m8flow_backend.startup.shared_realm_bootstrap import resolve_default_shared_realm_tenant_id

    flask_app = _flask_app_from_wrapped_application(app)

    secrets_file = os.getenv("M8FLOW_VAULT_DEMO_SECRETS_FILE")
    if not secrets_file or not os.path.exists(secrets_file):
        print("vault-demo-seed: No demo secrets file present; nothing to seed.", flush=True)
        return 0

    overwrite = os.getenv("M8FLOW_VAULT_DEMO_OVERWRITE", "").strip().lower() in {"1", "true", "yes", "on"}

    # Tenant lookup uses Flask-SQLAlchemy, so it must happen after entering the
    # application context. The helper intentionally returns None when called
    # without that context, which otherwise hides the real startup mistake.
    phase = "initializing"
    try:
        phase = "waiting for backend readiness"
        wait_for_backend_ready()
        with flask_app.app_context():
            phase = "resolving canonical tenant"
            tenant_alias = (
                os.getenv("M8FLOW_VAULT_DEMO_DEFAULT_TENANT_ALIAS") or default_organization_alias()
            ).strip()
            tenant_id = resolve_default_shared_realm_tenant_id()
            if not isinstance(tenant_id, str) or not tenant_id.strip():
                raise RuntimeError("The canonical m8flow demo tenant is not available.")

            secrets = load_seeded_secret_specs(
                Path(secrets_file),
                organization_alias=tenant_alias,
                organization_id=tenant_id,
                missing_file_message_factory=lambda _path: "Vault demo secrets file is missing.",
            )
            if not secrets:
                print("vault-demo-seed: No configured demo secrets; nothing to seed.", flush=True)
                return 0
            phase = "validating Vault configuration"
            if flask_app.config.get("M8FLOW_SECRET_BACKEND_KIND") != "vault":
                raise RuntimeError("Vault demo seeding requires M8FLOW_VAULT_ENABLED=true.")

            with flask_app.test_request_context("/"):
                phase = "reconciling configuration variables"
                g.m8flow_tenant_id = tenant_id
                result = reconcile_seeded_values(
                    secrets,
                    user_id=None,
                    overwrite=overwrite,
                    named_value_service=NamedValueService,
                )
                phase = "verifying seeded configuration variables"
                verify_seeded_values(secrets, named_value_service=NamedValueService)
                phase = "verifying authenticated configuration-variable list API"
                verify_authenticated_list_api(secrets, tenant_id)
    except Exception as exc:
        # Database and Vault client exceptions can embed request parameters.
        # Do not copy any exception detail into Compose logs.
        print(
            "vault-demo-seed: Failed to seed demo configuration variables. "
            "Verify secrets.yml, Vault availability, backend migrations, and the canonical m8flow tenant. "
            f"Failure category: {type(exc).__name__}; phase: {phase}.",
            file=os.sys.stderr,
            flush=True,
        )
        return 1

    print(
        "vault-demo-seed: Complete "
        f"(created={result.created}, reused={result.reused}, updated={result.updated}).",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
