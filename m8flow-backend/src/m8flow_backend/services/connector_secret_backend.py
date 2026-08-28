"""Where connector profile secrets are stored.

Every sensitive profile value goes through this seam rather than through
connector code directly. Today it delegates to the platform's existing
Fernet-backed secret service; swapping in another store (Vault KV v2, say)
means adding an implementation here and changing nothing else. That is the
whole preparation for Vault -- no second backend ships now.

Tenant scoping is not re-implemented here: models/tenant_schema.py adds
m8f_tenant_id to SecretModel and drops upstream's global unique on `key`, and
tenant_scoping_patch.py filters and stamps every query, so a lookup made in
tenant A's request context cannot see tenant B's secrets.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class SecretBackend(Protocol):
    """The operations connector profiles need from a secret store."""

    def create(self, key: str, value: str, user_id: int | None) -> None: ...

    def get(self, key: str) -> str | None: ...

    def upsert(self, key: str, value: str, user_id: int | None) -> None: ...

    def delete(self, key: str) -> None: ...


class PlatformSecretBackend:
    """SecretBackend over the platform's existing secret service."""

    def create(self, key: str, value: str, user_id: int | None) -> None:
        from spiffworkflow_backend.services.secret_service import SecretService

        SecretService.add_secret(key=key, value=value, user_id=user_id)

    # ponytail: get/delete read and remove the SecretModel row directly, while
    # create/upsert go through SecretService (which secret_service_patch swaps
    # out). Equivalent today because secrets live in the database. Route these
    # two through SecretService.get_secret/delete_secret before enabling the
    # Vault backend, or profiles will write to Vault and read back nothing.
    def get(self, key: str) -> str | None:
        from spiffworkflow_backend.models.db import db
        from spiffworkflow_backend.models.secret_model import SecretModel
        from spiffworkflow_backend.services.secret_service import SecretService

        secret = db.session.query(SecretModel).filter(SecretModel.key == key).first()
        if secret is None:
            return None
        return SecretService._decrypt(secret.value)

    def upsert(self, key: str, value: str, user_id: int | None) -> None:
        from spiffworkflow_backend.services.secret_service import SecretService

        SecretService.update_secret(
            key=key, value=value, user_id=user_id, create_if_not_exists=True
        )

    def delete(self, key: str) -> None:
        """Remove a secret. An absent key is not an error.

        Deletion is best effort by design: the configuration row is the record
        of truth, and a secret left behind by a failed delete is unreachable
        (nothing references it) rather than a leak of live credentials.
        """
        from spiffworkflow_backend.models.db import db
        from spiffworkflow_backend.models.secret_model import SecretModel

        secret = db.session.query(SecretModel).filter(SecretModel.key == key).first()
        if secret is None:
            return
        db.session.delete(secret)


_backend: SecretBackend = PlatformSecretBackend()


def secret_backend() -> SecretBackend:
    return _backend


def set_secret_backend(backend: SecretBackend) -> None:
    """Swap the backend. For tests, and for a future Vault rollout."""
    global _backend
    _backend = backend
