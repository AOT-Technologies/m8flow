from __future__ import annotations

from dataclasses import dataclass

from m8flow_backend.models.audit_mixin import AuditDateTimeMixin
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel, db


@dataclass
class M8flowNatsApiKeyModel(SpiffworkflowBaseDBModel, AuditDateTimeMixin):
    """A named, tenant-scoped NATS API key.

    Unlike the legacy ``m8flow_nats_tokens`` table (one key per tenant, keyed by
    tenant id), this model supports MANY keys per tenant so each integration
    (CI, SDK, a microservice, ...) can hold, rotate, and revoke its own key
    independently.

    A raw key looks like ``m8f_<id>.<secret>``:
    - ``id`` is the public key identifier, stored here and used for O(1) lookup.
    - ``<secret>`` is high-entropy and never stored; only its HMAC-SHA256 hash is.
    """

    __tablename__ = "m8flow_nats_api_keys"

    # The public key id (the ``<id>`` segment of ``m8f_<id>.<secret>``).
    id: str = db.Column(db.String(64), primary_key=True, nullable=False)

    m8f_tenant_id: str = db.Column(
        db.String(255),
        db.ForeignKey("m8flow_tenant.id"),
        nullable=False,
        index=True,
    )

    # Human-friendly name for the key, e.g. "CI pipeline".
    label: str = db.Column(db.String(255), nullable=False)

    # HMAC-SHA256 of the secret segment. The raw secret is never stored.
    token_hash: str = db.Column(db.String(255), nullable=False, unique=True)

    # Optional scope: a comma-separated list of allowed process identifiers.
    # NULL (or "*") means the key may trigger any process in its tenant.
    scope: str | None = db.Column(db.String(2048), nullable=True)

    # Epoch seconds at which the key expires. NULL means it never expires.
    expires_at_in_seconds: int | None = db.Column(db.Integer, nullable=True)
    # Epoch seconds of the most recent successful authentication with this key.
    last_used_at_in_seconds: int | None = db.Column(db.Integer, nullable=True)
    # Epoch seconds at which the key was revoked. NULL means active.
    revoked_at_in_seconds: int | None = db.Column(db.Integer, nullable=True)

    created_by: str = db.Column(db.String(255), nullable=False)
    modified_by: str = db.Column(db.String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<M8flowNatsApiKeyModel(id={self.id}, tenant_id={self.m8f_tenant_id})>"
