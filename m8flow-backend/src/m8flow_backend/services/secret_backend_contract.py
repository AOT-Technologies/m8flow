from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SecretRecord(Protocol):
    """Common secret object shape expected by M8Flow callers."""

    id: str | int
    key: str
    user_id: int
    value: str
    updated_at_in_seconds: int | None
    created_at_in_seconds: int | None

    def to_dict(self) -> dict[str, Any]:
        """Return the API-facing metadata payload for a stored secret."""


@runtime_checkable
class SecretBackend(Protocol):
    """Common provider contract for tenant secret storage backends."""

    def add_secret(self, key: str, value: str, user_id: int) -> SecretRecord:
        """Create a new secret and return its stored record."""

    def get_secret(self, key: str) -> SecretRecord:
        """Return the stored secret record for the given key."""

    def update_secret(
        self,
        key: str,
        value: str,
        user_id: int | None = None,
        create_if_not_exists: bool | None = False,
    ) -> None:
        """Update an existing secret value, optionally creating it."""

    def delete_secret(self, key: str, user_id: int) -> None:
        """Delete a stored secret."""

    def serialize_secret_list_result(
        self,
        page: int = 1,
        per_page: int = 100,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the API-facing paginated list payload for secrets."""

    def get_secret_value(self, key: str) -> str:
        """Return the decrypted/raw secret value for the given key."""
