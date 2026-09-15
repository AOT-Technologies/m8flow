"""Secret storage provider — the seam Vault (and others) plug into later.

HTTP and runtime always talk to ``get_secret_provider()``. The default kind is
``database``. Set ``M8FLOW_SECRET_BACKEND_KIND`` to select another registered
kind. Unknown kinds fail closed rather than silently using Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from m8flow_backend.errors import ApiError

DEFAULT_SECRET_BACKEND_KIND = "database"


@dataclass(frozen=True)
class SecretRecord:
    """API-facing secret metadata. Never carries the stored value."""

    id: str | int
    key: str
    user_id: int
    tenant_id: str
    created_at_in_seconds: int | None
    updated_at_in_seconds: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "user_id": self.user_id,
            "created_at_in_seconds": self.created_at_in_seconds,
            "updated_at_in_seconds": self.updated_at_in_seconds,
        }


@dataclass(frozen=True)
class SecretListPage:
    records: tuple[SecretRecord, ...]
    total: int
    page: int
    per_page: int

    def pagination(self) -> dict[str, int]:
        pages = max(1, (self.total + self.per_page - 1) // self.per_page) if self.total else 0
        return {"count": len(self.records), "total": self.total, "pages": pages}


@runtime_checkable
class SecretProvider(Protocol):
    """Tenant-scoped secret storage. Implementations must never return values on list/get."""

    def add(
        self,
        session: Any,
        *,
        tenant_id: str,
        key: str,
        value: str,
        user_id: int,
    ) -> SecretRecord: ...

    def get(self, session: Any, *, tenant_id: str, key: str) -> SecretRecord: ...

    def get_value(self, session: Any, *, tenant_id: str, key: str) -> str | None: ...

    def update(self, session: Any, *, tenant_id: str, key: str, value: str) -> None: ...

    def delete(self, session: Any, *, tenant_id: str, key: str) -> None: ...

    def list(
        self,
        session: Any,
        *,
        tenant_id: str,
        page: int = 1,
        per_page: int = 100,
    ) -> SecretListPage: ...

    def list_keys(self, session: Any, *, tenant_id: str) -> list[str]: ...


_PROVIDERS: dict[str, Callable[[], SecretProvider]] = {}


def register_secret_provider(kind: str, factory: Callable[[], SecretProvider]) -> None:
    normalized = kind.strip().lower()
    if not normalized:
        raise ValueError("secret backend kind must be non-empty")
    _PROVIDERS[normalized] = factory


def registered_secret_backend_kinds() -> frozenset[str]:
    return frozenset(_PROVIDERS)


def resolved_secret_backend_kind(kind: str | None = None) -> str:
    import os

    from m8flow_backend.config import vault_enabled

    explicit = (kind or os.environ.get("M8FLOW_SECRET_BACKEND_KIND") or "").strip().lower()
    if explicit:
        return explicit
    if vault_enabled():
        return "vault"
    return DEFAULT_SECRET_BACKEND_KIND


def get_secret_provider(kind: str | None = None) -> SecretProvider:
    resolved = resolved_secret_backend_kind(kind)
    factory = _PROVIDERS.get(resolved)
    if factory is None:
        known = ", ".join(sorted(_PROVIDERS)) or "(none)"
        raise ApiError(
            "secret_backend_unavailable",
            f"Unknown secret backend {resolved!r}. Registered: {known}.",
            500,
        )
    return factory()
