from __future__ import annotations
import secrets
import string
from m8flow_backend.models.nats_token import NatsTokenModel
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.exceptions.api_error import ApiError
from m8flow_backend.config import nats_token_salt

import hashlib
import hmac

class NatsTokenService:
    @staticmethod
    def _hash_token(raw_token: str, salt: str) -> str:
        """Hash a raw token using HMAC-SHA256 with the provided salt."""
        mac = hmac.new(
            key=salt.encode('utf-8'),
            msg=raw_token.encode('utf-8'),
            digestmod=hashlib.sha256
        )
        return mac.hexdigest()

    @staticmethod
    def generate_token(tenant_id: str, user_id: str) -> tuple[NatsTokenModel, str]:
        """
        Generate or regenerate a unique NATS token for a tenant.
        Returns a tuple of (NatsTokenModel, raw_token_string).
        The raw token is NEVER stored in the database.
        """
        # Structured prefix for identification
        prefix = "m8f_"
        # High entropy key
        raw_key = secrets.token_urlsafe(32)
        raw_token = f"{prefix}{raw_key}"
        
        salt = nats_token_salt()
        hashed_token = NatsTokenService._hash_token(raw_token, salt)
        
        # Look for existing token for this tenant
        nats_token = NatsTokenModel.query.filter_by(m8f_tenant_id=tenant_id).first()
        
        if nats_token:
            nats_token.token = hashed_token
            nats_token.modified_by = user_id
        else:
            nats_token = NatsTokenModel(
                m8f_tenant_id=tenant_id,
                token=hashed_token,
                created_by=user_id,
                modified_by=user_id
            )
            db.session.add(nats_token)
            
        try:
            db.session.commit()
            return nats_token, raw_token
        except Exception as e:
            db.session.rollback()
            raise ApiError(
                error_code="database_error",
                message=f"Error saving NATS token: {str(e)}",
                status_code=500
            )

    @staticmethod
    def verify_token(tenant_id: str, raw_token: str) -> bool:
        """Verify a raw token against the stored hash for a tenant."""
        import logging
        logger = logging.getLogger("m8flow.nats.token_service")

        nats_token = NatsTokenModel.query.filter_by(m8f_tenant_id=tenant_id).first()
        if not nats_token:
            logger.error("verify_token: No token record found for tenant=%s", tenant_id)
            return False

        salt = nats_token_salt()
        expected_hash = NatsTokenService._hash_token(raw_token, salt)

        logger.debug(
            "verify_token: stored=%s expected=%s match=%s",
            nats_token.token[:12] + "...",
            expected_hash[:12] + "...",
            nats_token.token == expected_hash,
        )

        return hmac.compare_digest(nats_token.token, expected_hash)

    @staticmethod
    def get_token_for_tenant(tenant_id: str) -> NatsTokenModel | None:
        """Retrieve the hashed NATS token record for a specific tenant."""
        return NatsTokenModel.query.filter_by(m8f_tenant_id=tenant_id).first()
