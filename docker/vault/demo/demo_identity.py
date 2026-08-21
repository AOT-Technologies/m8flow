from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib import error, request


DEFAULT_KEYCLOAK_URL = "http://keycloak:8080"


@dataclass(frozen=True)
class DemoTenantIdentity:
    organization_id: str
    organization_alias: str
    organization_name: str
    admin_username: str
    admin_email: str | None
    admin_service: str
    admin_service_id: str


def ensure_backend_src_on_path() -> None:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    backend_src = repo_root / "m8flow-backend" / "src"
    backend_src_str = str(backend_src)
    if backend_src_str not in sys.path:
        sys.path.insert(0, backend_src_str)


def _required_non_empty_string(value: Any, message: str) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    raise RuntimeError(message)


def _keycloak_base_url() -> str:
    return (os.getenv("KEYCLOAK_URL") or os.getenv("M8FLOW_KEYCLOAK_URL") or DEFAULT_KEYCLOAK_URL).rstrip("/")


def _realm_issuer(realm: str) -> str:
    normalized_realm = _required_non_empty_string(realm, "A shared realm name is required.")
    configured_issuer = os.getenv("M8FLOW_VAULT_DEMO_REALM_ISSUER") or os.getenv(
        "SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__uri"
    )
    if configured_issuer and configured_issuer.strip():
        return configured_issuer.strip().rstrip("/")

    public_base = os.getenv("KEYCLOAK_HOSTNAME") or os.getenv("M8FLOW_KEYCLOAK_PUBLIC_ISSUER_BASE")
    if public_base and public_base.strip():
        return f"{public_base.strip().rstrip('/')}/realms/{normalized_realm}"

    url = f"{_keycloak_base_url()}/realms/{normalized_realm}/.well-known/openid-configuration"
    req = request.Request(url, method="GET")
    try:
        with request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raise RuntimeError(
            f"Keycloak discovery for realm '{normalized_realm}' returned {exc.code} at {url}."
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(
            f"Could not reach Keycloak discovery for realm '{normalized_realm}' at {url}: {exc}"
        ) from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Keycloak discovery for realm '{normalized_realm}' returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Keycloak discovery for realm '{normalized_realm}' did not return an object.")

    return _required_non_empty_string(
        payload.get("issuer"),
        f"Keycloak discovery for realm '{normalized_realm}' did not return an issuer.",
    )


def resolve_demo_tenant_identity(
    *,
    organization_alias: str | None = None,
    admin_username: str | None = None,
) -> DemoTenantIdentity:
    ensure_backend_src_on_path()

    from m8flow_backend.config import default_organization_alias, shared_realm_name
    from m8flow_backend.services.keycloak_service import (
        get_master_admin_token,
        get_organization_by_alias,
        get_organization_member_by_username,
        get_realm_user_by_username,
    )

    realm = _required_non_empty_string(shared_realm_name(), "The shared Keycloak realm is not configured.")
    resolved_alias = organization_alias or os.getenv("M8FLOW_VAULT_DEMO_DEFAULT_TENANT_ALIAS") or default_organization_alias()
    resolved_alias = _required_non_empty_string(
        resolved_alias,
        "The default shared-realm organization alias is not configured.",
    )
    resolved_admin_username = admin_username or os.getenv("M8FLOW_VAULT_DEMO_ADMIN_USERNAME") or os.getenv("KEYCLOAK_ADMIN_USER") or "admin"
    resolved_admin_username = _required_non_empty_string(
        resolved_admin_username,
        "The Vault demo admin username is not configured.",
    )

    token = get_master_admin_token()
    organization = get_organization_by_alias(resolved_alias, admin_token=token)
    if organization is None:
        raise RuntimeError(f"Keycloak organization '{resolved_alias}' could not be found in realm '{realm}'.")

    organization_id = _required_non_empty_string(
        organization.get("id"),
        f"Keycloak organization '{resolved_alias}' did not return a usable id.",
    )
    organization_name = _required_non_empty_string(
        organization.get("name") or resolved_alias,
        f"Keycloak organization '{resolved_alias}' did not return a usable name.",
    )

    member = get_organization_member_by_username(
        organization_id,
        resolved_admin_username,
        admin_token=token,
    )
    if member is None:
        member = get_realm_user_by_username(
            realm,
            resolved_admin_username,
            admin_token=token,
        )
    if member is None:
        raise RuntimeError(
            f"Keycloak user '{resolved_admin_username}' could not be found in realm '{realm}'."
        )

    admin_service_id = _required_non_empty_string(
        member.get("id"),
        f"Keycloak user '{resolved_admin_username}' did not return a usable id.",
    )
    admin_email = member.get("email")
    if isinstance(admin_email, str):
        normalized_email = admin_email.strip()
        admin_email = normalized_email or None
    else:
        admin_email = None

    return DemoTenantIdentity(
        organization_id=organization_id,
        organization_alias=resolved_alias,
        organization_name=organization_name,
        admin_username=resolved_admin_username,
        admin_email=admin_email,
        admin_service=_realm_issuer(realm),
        admin_service_id=admin_service_id,
    )


def wait_for_demo_tenant_identity(
    *,
    timeout_seconds: float,
    interval_seconds: float,
    organization_alias: str | None = None,
    admin_username: str | None = None,
) -> DemoTenantIdentity:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None

    while time.time() < deadline:
        try:
            return resolve_demo_tenant_identity(
                organization_alias=organization_alias,
                admin_username=admin_username,
            )
        except Exception as exc:
            last_error = str(exc)
            time.sleep(interval_seconds)

    raise RuntimeError(
        "Timed out waiting for the Vault demo tenant identity to become available. "
        f"Last error: {last_error or 'unknown error'}"
    )
