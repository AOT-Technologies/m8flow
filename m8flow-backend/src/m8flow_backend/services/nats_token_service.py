from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass

from m8flow_backend.config import nats_token_salt
from m8flow_backend.models.nats_api_key import M8flowNatsApiKeyModel
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db

LOGGER = logging.getLogger("m8flow.nats.token_service")

# Raw key format: ``m8f_<id>.<secret>``.
KEY_PREFIX = "m8f_"
# Minimum interval between ``last_used_at_in_seconds`` writes for a single key.
# Auth happens on every webhook call; without throttling that is one DB write per
# request. Stamping at most once per window keeps last-used useful while avoiding
# write amplification under load.
LAST_USED_STAMP_THROTTLE_SECONDS = 60
# The delimiter separating the public key id from the secret. It is deliberately
# outside the base64url alphabet used by ``secrets.token_urlsafe``/``token_hex``,
# so it never appears inside either segment.
KEY_DELIMITER = "."


@dataclass(frozen=True)
class AuthenticatedKey:
    """The identity resolved from a valid NATS API key."""

    tenant_id: str
    key_id: str
    created_by: str
    scope: str | None


class NatsTokenService:
    @staticmethod
    def _hash_token(raw_token: str, salt: str) -> str:
        """Hash a high-entropy API secret using HMAC-SHA256 with a server pepper.

        ``raw_token`` is the secret segment of a NATS API key: a 256-bit value from
        ``secrets.token_urlsafe(32)`` (see ``create_named_key``), NOT a user-chosen
        password. The hash exists so the raw secret is never stored and can be
        compared in constant time, not to resist password brute-force. Because the
        secret is not brute-forceable, a slow password KDF (bcrypt/scrypt/argon2)
        would add cost on every webhook auth with no security benefit. HMAC-SHA256
        with a secret pepper is the standard construction for high-entropy API keys.
        """
        # codeql[py/weak-sensitive-data-hashing]: the input is a 256-bit random
        # secret, not a password, so a slow KDF adds no value here (see docstring).
        mac = hmac.new(
            key=salt.encode('utf-8'),
            msg=raw_token.encode('utf-8'),
            digestmod=hashlib.sha256
        )
        return mac.hexdigest()

    @staticmethod
    def create_named_key(
        tenant_id: str,
        user_id: str,
        label: str,
        expires_in_seconds: int | None = None,
        scope: str | None = None,
    ) -> tuple[M8flowNatsApiKeyModel, str]:
        """
        Create a new named NATS API key for a tenant.

        Returns a tuple of (M8flowNatsApiKeyModel, raw_key_string). The raw key is
        returned exactly once and is NEVER stored; only the HMAC of its secret
        segment is persisted.

        ``expires_in_seconds`` is the key lifetime from now (``None`` = never
        expires). ``scope`` is an optional comma-separated list of allowed process
        identifiers (``None``/``"*"`` = any process in the tenant).
        """
        # High-entropy public id (hex, no delimiter chars) and secret.
        key_id = secrets.token_hex(6)
        secret = secrets.token_urlsafe(32)
        raw_key = f"{KEY_PREFIX}{key_id}{KEY_DELIMITER}{secret}"

        salt = nats_token_salt()
        token_hash = NatsTokenService._hash_token(secret, salt)

        expires_at_in_seconds = (
            int(time.time()) + expires_in_seconds
            if expires_in_seconds is not None
            else None
        )

        normalized_scope = scope.strip() if isinstance(scope, str) else None
        if not normalized_scope or normalized_scope == "*":
            normalized_scope = None

        api_key = M8flowNatsApiKeyModel(
            id=key_id,
            m8f_tenant_id=tenant_id,
            label=label,
            token_hash=token_hash,
            scope=normalized_scope,
            expires_at_in_seconds=expires_at_in_seconds,
            created_by=user_id,
            modified_by=user_id,
        )
        db.session.add(api_key)

        try:
            db.session.commit()
            return api_key, raw_key
        except Exception:
            db.session.rollback()
            # Log the underlying DB detail server-side only; never surface it to the
            # client (it can expose schema/internal details).
            LOGGER.exception("create_named_key: failed to save NATS API key")
            raise ApiError(
                error_code="database_error",
                message="Could not save the NATS API key.",
                status_code=500,
            )

    @staticmethod
    def list_keys(tenant_id: str) -> list[M8flowNatsApiKeyModel]:
        """Return all API keys for a tenant, newest first. Never exposes secrets."""
        return (
            M8flowNatsApiKeyModel.query.filter_by(m8f_tenant_id=tenant_id)
            .order_by(M8flowNatsApiKeyModel.created_at_in_seconds.desc())
            .all()
        )

    @staticmethod
    def revoke_key(tenant_id: str, key_id: str, user_id: str) -> bool:
        """Revoke a single key owned by the tenant.

        Returns True if a key was revoked. Raises 404 if the key does not exist
        for this tenant (tenant-scoped so callers cannot revoke another tenant's
        key).
        """
        api_key = M8flowNatsApiKeyModel.query.filter_by(
            id=key_id, m8f_tenant_id=tenant_id
        ).first()
        if not api_key:
            raise ApiError(
                error_code="nats_api_key_not_found",
                message="No NATS API key with that id exists for this tenant.",
                status_code=404,
            )

        if api_key.revoked_at_in_seconds is not None:
            return False

        api_key.revoked_at_in_seconds = int(time.time())
        api_key.modified_by = user_id
        try:
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            # Log the underlying DB detail server-side only; never surface it to the
            # client (it can expose schema/internal details).
            LOGGER.exception("revoke_key: failed to revoke NATS API key")
            raise ApiError(
                error_code="database_error",
                message="Could not revoke the NATS API key.",
                status_code=500,
            )

    @staticmethod
    def authenticate_key(raw_key: str) -> AuthenticatedKey | None:
        """Resolve a raw API key to its tenant and owning identity.

        Returns an ``AuthenticatedKey`` for a valid, non-expired, non-revoked key,
        or ``None`` for any missing / malformed / unknown / expired / revoked key.

        Keys are ``m8f_<id>.<secret>`` and are resolved by their public id, then the
        secret is compared in constant time against the stored hash.
        """
        if not isinstance(raw_key, str) or not raw_key.startswith(KEY_PREFIX):
            return None

        body = raw_key[len(KEY_PREFIX):]
        key_id, delimiter, secret = body.partition(KEY_DELIMITER)
        if not delimiter or not key_id or not secret:
            return None

        api_key = M8flowNatsApiKeyModel.query.filter_by(id=key_id).first()
        if not api_key:
            return None

        expected_hash = NatsTokenService._hash_token(secret, nats_token_salt())
        if not hmac.compare_digest(api_key.token_hash, expected_hash):
            return None

        if api_key.revoked_at_in_seconds is not None:
            LOGGER.warning("authenticate_key: key %s is revoked", api_key.id)
            return None

        now = int(time.time())
        if (
            api_key.expires_at_in_seconds is not None
            and now > api_key.expires_at_in_seconds
        ):
            LOGGER.warning("authenticate_key: key %s is expired", api_key.id)
            return None

        # Best-effort, throttled last-used stamp; never fail auth because the stamp
        # fails. Only write when unset or the previous stamp is older than the
        # throttle window, so a busy key does not issue a DB write per request.
        last_used = api_key.last_used_at_in_seconds
        if last_used is None or now - last_used >= LAST_USED_STAMP_THROTTLE_SECONDS:
            try:
                api_key.last_used_at_in_seconds = now
                db.session.commit()
            except Exception:
                db.session.rollback()

        return AuthenticatedKey(
            tenant_id=api_key.m8f_tenant_id,
            key_id=api_key.id,
            created_by=api_key.created_by,
            scope=api_key.scope,
        )

    @staticmethod
    def scope_allows(scope: str | None, process_identifier: str) -> bool:
        """Return whether a key ``scope`` permits triggering ``process_identifier``.

        ``None`` or ``"*"`` allows any process. Otherwise ``scope`` is a
        comma-separated allow-list; a ``"*"`` entry also allows any process.
        """
        if scope is None:
            return True
        allowed = {entry.strip() for entry in scope.split(",") if entry.strip()}
        if not allowed or "*" in allowed:
            return True
        return process_identifier in allowed
