from __future__ import annotations

from urllib.parse import quote
import re


_SAFE_CONNECTOR_IDENTIFIER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?$")


def vault_safe_tenant_path_component(tenant_id: str) -> str:
    """Encode a tenant id so Vault path/policy wildcards cannot reinterpret it."""

    normalized_tenant_id = str(tenant_id or "").strip()
    if not normalized_tenant_id:
        raise ValueError("tenant_id must not be empty.")
    return quote(normalized_tenant_id, safe="._-")


def vault_safe_connector_identifier(identifier: str) -> str:
    """Validate an immutable connector identifier as one Vault path component."""

    normalized_identifier = str(identifier or "").strip()
    if not _SAFE_CONNECTOR_IDENTIFIER.fullmatch(normalized_identifier):
        raise ValueError(
            "connector identifier must be 1-64 characters of letters, digits, '.', '-' or '_', "
            "starting and ending with a letter or digit."
        )
    return normalized_identifier
