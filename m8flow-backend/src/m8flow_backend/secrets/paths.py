"""KV v2 path helpers for tenant-scoped secrets."""

from __future__ import annotations

import re
from urllib.parse import quote

from m8flow_backend.config import vault_secret_path_prefix

_SECRET_KEY_PATTERN = re.compile(r"^\w+$")


def join_vault_path(*parts: str) -> str:
    return "/".join(part.strip().strip("/") for part in parts if part and part.strip().strip("/"))


def encode_tenant_component(tenant_id: str) -> str:
    normalized = (tenant_id or "").strip()
    if not normalized:
        raise ValueError("tenant_id must not be empty.")
    return quote(normalized, safe="._-")


def secret_root(tenant_id: str, *, prefix: str | None = None) -> str:
    return join_vault_path(
        prefix or vault_secret_path_prefix(),
        "tenants",
        encode_tenant_component(tenant_id),
        "secrets",
    )


def secret_path(tenant_id: str, key: str, *, prefix: str | None = None) -> str:
    cleaned = (key or "").strip()
    if not cleaned:
        raise ValueError("secret key must not be empty.")
    if ".." in cleaned or "/" in cleaned or not _SECRET_KEY_PATTERN.fullmatch(cleaned):
        raise ValueError("secret key must be a word (letters, digits, underscore).")
    return join_vault_path(secret_root(tenant_id, prefix=prefix), cleaned)
