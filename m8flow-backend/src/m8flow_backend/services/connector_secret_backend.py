"""Where connector profile secrets are stored.

Every sensitive profile value goes through this seam, never through the
connector code directly. Today it delegates to the platform's existing
Fernet-backed secret store; swapping in a different store (Vault KV v2, for
one) means adding an implementation here and changing nothing else.

Tenant scoping is not re-implemented: the secret table carries m8f_tenant_id
and m8flow's tenant scoping patch filters and stamps every query, so a lookup
made in tenant A's request context cannot see tenant B's secrets.
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
    """SecretBackend on top of the platform's secret service."""

    def create(self, key: str, value: str, user_id: int | None) -> None:
        from spiffworkflow_backend.services.secret_service import SecretService

        SecretService.add_secret(key=key, value=value, user_id=user_id)

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
        """Remove a secret. Absent keys are not an error.

        Deletion is best effort by design: the configuration row is the record
        of truth, and a secret left behind by a failed delete is swept up by
        the orphan check rather than blocking the user's action.
        """
        from spiffworkflow_backend.models.db import db
        from spiffworkflow_backend.models.secret_model import SecretModel

        secret = db.session.query(SecretModel).filter(SecretModel.key == key).first()
        if secret is None:
            return
        db.session.delete(secret)
        db.session.commit()


_backend: SecretBackend = PlatformSecretBackend()


def secret_backend() -> SecretBackend:
    return _backend


def set_secret_backend(backend: SecretBackend) -> None:
    """Swap the backend. Used by tests and by a future Vault rollout."""
    global _backend
    _backend = backend
