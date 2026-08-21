from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

@dataclass(frozen=True)
class SeededSecretSpec:
    tenant_reference: str
    tenant_id: str
    secret_name: str
    value: str


def _normalized_non_empty(value: object, message: str) -> str:
    normalized = str(value).strip()
    if normalized:
        return normalized
    raise RuntimeError(message)


def load_seeded_secret_specs(
    secrets_file: Path,
    *,
    organization_alias: str,
    organization_id: str,
    missing_file_message_factory: Callable[[Path], str],
    logger: Callable[[str], None] | None = None,
) -> list[SeededSecretSpec]:
    resolved_alias = _normalized_non_empty(organization_alias, "A demo organization alias is required.")
    resolved_organization_id = _normalized_non_empty(organization_id, "A demo organization id is required.")

    if not secrets_file.exists():
        if logger is not None:
            logger(
                f"{missing_file_message_factory(secrets_file)} "
                f"Proceeding without seeding any demo secrets for tenant '{resolved_alias}'."
            )
        return []

    raw_payload = yaml.safe_load(secrets_file.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_payload, dict):
        raise RuntimeError(f"Vault demo secrets file must contain a top-level mapping: {secrets_file}")

    tenants = raw_payload.get("tenants")
    if not isinstance(tenants, dict) or not tenants:
        raise RuntimeError(f"Vault demo secrets file must define at least one tenant under 'tenants': {secrets_file}")

    seeded_secrets: list[SeededSecretSpec] = []
    for tenant_reference, tenant_payload in tenants.items():
        normalized_tenant_reference = _normalized_non_empty(
            tenant_reference,
            f"Invalid tenant id in {secrets_file}: {tenant_reference!r}",
        )
        if "/" in normalized_tenant_reference:
            raise RuntimeError(f"Invalid tenant id in {secrets_file}: {tenant_reference!r}")

        resolved_tenant_id = (
            resolved_organization_id
            if normalized_tenant_reference == resolved_alias
            else normalized_tenant_reference
        )

        if isinstance(tenant_payload, dict) and "secrets" in tenant_payload:
            secrets_payload = tenant_payload.get("secrets")
        else:
            secrets_payload = tenant_payload

        if not isinstance(secrets_payload, dict) or not secrets_payload:
            raise RuntimeError(
                f"Tenant '{normalized_tenant_reference}' must define at least one secret in {secrets_file}."
            )

        for secret_name, secret_value in secrets_payload.items():
            normalized_secret_name = _normalized_non_empty(
                secret_name,
                f"Invalid secret name for tenant '{normalized_tenant_reference}' in {secrets_file}: {secret_name!r}",
            )
            if "/" in normalized_secret_name:
                raise RuntimeError(
                    f"Invalid secret name for tenant '{normalized_tenant_reference}' in {secrets_file}: {secret_name!r}"
                )
            seeded_secrets.append(
                SeededSecretSpec(
                    tenant_reference=normalized_tenant_reference,
                    tenant_id=resolved_tenant_id,
                    secret_name=normalized_secret_name,
                    value=str(secret_value),
                )
            )

    return seeded_secrets
