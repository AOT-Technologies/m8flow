from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys before a seed value can be overwritten silently."""


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, deep: bool = False):
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise RuntimeError("Vault demo secrets file contains a duplicate mapping key.")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)

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

    try:
        raw_payload = yaml.load(secrets_file.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError("Vault demo secrets file contains invalid YAML.") from exc
    if not isinstance(raw_payload, dict):
        raise RuntimeError(f"Vault demo secrets file must contain a top-level mapping: {secrets_file}")

    tenants = raw_payload.get("tenants")
    if not isinstance(tenants, dict) or not tenants:
        return []

    seeded_secrets: list[SeededSecretSpec] = []
    for tenant_reference, tenant_payload in tenants.items():
        normalized_tenant_reference = _normalized_non_empty(
            tenant_reference,
            f"Invalid tenant id in {secrets_file}: {tenant_reference!r}",
        )
        if "/" in normalized_tenant_reference:
            raise RuntimeError(f"Invalid tenant id in {secrets_file}: {tenant_reference!r}")

        if isinstance(tenant_payload, dict) and "secrets" in tenant_payload:
            secrets_payload = tenant_payload.get("secrets")
        else:
            secrets_payload = tenant_payload

        if secrets_payload is None:
            continue
        if not isinstance(secrets_payload, dict):
            raise RuntimeError(f"Tenant '{normalized_tenant_reference}' secrets must be a mapping.")
        if not secrets_payload:
            continue
        if normalized_tenant_reference != resolved_alias:
            raise RuntimeError(
                f"Vault demo secrets may only seed the canonical tenant '{resolved_alias}'."
            )

        resolved_tenant_id = resolved_organization_id

        for secret_name, secret_value in secrets_payload.items():
            normalized_secret_name = _normalized_non_empty(
                secret_name,
                f"Invalid secret name for tenant '{normalized_tenant_reference}' in {secrets_file}: {secret_name!r}",
            )
            if "/" in normalized_secret_name:
                raise RuntimeError(
                    f"Invalid secret name for tenant '{normalized_tenant_reference}' in {secrets_file}: {secret_name!r}"
                )
            if secret_value is None:
                raise RuntimeError(
                    f"Configuration variable '{normalized_secret_name}' must have a value."
                )
            seeded_secrets.append(
                SeededSecretSpec(
                    tenant_reference=normalized_tenant_reference,
                    tenant_id=resolved_tenant_id,
                    secret_name=normalized_secret_name,
                    value=str(secret_value),
                )
            )

    seen_names: set[tuple[str, str]] = set()
    for secret in seeded_secrets:
        uniqueness_key = (secret.tenant_id, secret.secret_name.casefold())
        if uniqueness_key in seen_names:
            raise RuntimeError(
                "Vault demo secrets file contains duplicate configuration-variable names for the same tenant."
            )
        seen_names.add(uniqueness_key)

    return seeded_secrets
