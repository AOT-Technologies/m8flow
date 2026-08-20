from __future__ import annotations

from urllib.parse import quote


def vault_safe_tenant_path_component(tenant_id: str) -> str:
    """Encode a tenant id so Vault path/policy wildcards cannot reinterpret it."""

    normalized_tenant_id = str(tenant_id or "").strip()
    if not normalized_tenant_id:
        raise ValueError("tenant_id must not be empty.")
    return quote(normalized_tenant_id, safe="._-")
