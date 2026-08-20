from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from flask import g, has_request_context, request

from m8flow_backend.models.audit_log import AuditLogModel
from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from spiffworkflow_backend.models.db import db


logger = logging.getLogger("m8flow.audit_log")
REDACTED_AUDIT_VALUE = "[redacted]"
_SENSITIVE_AUDIT_TEXT_FIELDS = (
    "secret_id",
    "role_id",
    "root_token",
    "client_token",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "authorization",
    "api_key",
    "credential",
    "value",
)
_SENSITIVE_AUDIT_KEYS = frozenset(
    {
        "secret_value",
        "password",
        "authorization",
        "credential",
        "api_key",
        "secret_id",
        "role_id",
        "root_token",
        "client_token",
        "access_token",
        "refresh_token",
        "private_key",
    }
)
_SENSITIVE_AUDIT_KEY_SUFFIXES = (
    "_token",
    "_password",
    "_secret",
    "_secret_id",
    "_api_key",
    "_authorization",
    "_credential",
)


def _normalized_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def is_sensitive_audit_key(key: Any) -> bool:
    normalized_key = _normalized_key(key)
    if not normalized_key:
        return False
    if normalized_key in _SENSITIVE_AUDIT_KEYS:
        return True
    return normalized_key.endswith(_SENSITIVE_AUDIT_KEY_SUFFIXES)


def redact_audit_text(message: str | None) -> str | None:
    if message is None:
        return None

    sanitized = " ".join(str(message).split())
    joined_fields = "|".join(re.escape(field) for field in _SENSITIVE_AUDIT_TEXT_FIELDS)
    sanitized = re.sub(
        rf"((?:{joined_fields})\s*=\s*)([^,\s]+)",
        rf"\1{REDACTED_AUDIT_VALUE}",
        sanitized,
        flags=re.I,
    )
    sanitized = re.sub(
        rf'("(?:{joined_fields})"\s*:\s*")([^"]+)(")',
        rf"\1{REDACTED_AUDIT_VALUE}\3",
        sanitized,
        flags=re.I,
    )
    sanitized = re.sub(
        r"(Bearer\s+)([A-Za-z0-9._~+\/=-]+)",
        rf"\1{REDACTED_AUDIT_VALUE}",
        sanitized,
        flags=re.I,
    )
    return sanitized


def redact_audit_details(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return redact_audit_text(value)

    if isinstance(value, Mapping):
        sanitized_mapping: dict[str, Any] = {}
        for key, nested_value in value.items():
            normalized_key = str(key)
            if is_sensitive_audit_key(normalized_key):
                sanitized_mapping[normalized_key] = REDACTED_AUDIT_VALUE
            else:
                sanitized_mapping[normalized_key] = redact_audit_details(nested_value)
        return sanitized_mapping

    if isinstance(value, set):
        return [redact_audit_details(item) for item in sorted(value, key=lambda item: str(item))]

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact_audit_details(item) for item in value]

    return redact_audit_text(str(value))


class AuditLogService:
    """Persist application audit events with context defaults and safe redaction."""

    def record_event(
        self,
        *,
        category: str,
        event_type: str,
        source: str,
        status: str,
        severity: str = "info",
        message: str | None = None,
        tenant_id: str | None = None,
        actor_type: str | None = None,
        actor_id: str | int | None = None,
        actor_username: str | None = None,
        resource_type: str | None = None,
        resource_id: str | int | None = None,
        resource_name: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        details: Any = None,
        auto_commit: bool = True,
    ) -> AuditLogModel:
        actor = self._current_actor()
        record = AuditLogModel(
            id=uuid.uuid4().hex,
            category=self._required_string(category, "category"),
            event_type=self._required_string(event_type, "event_type"),
            source=self._required_string(source, "source"),
            status=self._required_string(status, "status"),
            severity=self._optional_string(severity) or "info",
            message=redact_audit_text(message),
            m8f_tenant_id=self._optional_string(tenant_id) or self._current_tenant_id(),
            actor_type=self._optional_string(actor_type) or actor["actor_type"],
            actor_id=self._stringify_identifier(actor_id) or actor["actor_id"],
            actor_username=self._optional_string(actor_username) or actor["actor_username"],
            resource_type=self._optional_string(resource_type),
            resource_id=self._stringify_identifier(resource_id),
            resource_name=self._optional_string(resource_name),
            request_id=self._optional_string(request_id) or self._current_request_id(),
            correlation_id=self._optional_string(correlation_id) or self._current_correlation_id(),
            details=redact_audit_details(details),
        )
        db.session.add(record)

        if auto_commit:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

        return record

    def try_record_event(self, **kwargs: Any) -> AuditLogModel | None:
        try:
            return self.record_event(**kwargs)
        except Exception as exc:
            logger.warning(
                "audit_log_service: failed to record event category=%s event_type=%s error_type=%s",
                kwargs.get("category"),
                kwargs.get("event_type"),
                type(exc).__name__,
            )
            return None

    def latest_event(
        self,
        *,
        category: str | None = None,
        event_type: str | None = None,
        source: str | None = None,
    ) -> AuditLogModel | None:
        query = AuditLogModel.query

        if isinstance(category, str) and category.strip():
            query = query.filter(AuditLogModel.category == category.strip())
        if isinstance(event_type, str) and event_type.strip():
            query = query.filter(AuditLogModel.event_type == event_type.strip())
        if isinstance(source, str) and source.strip():
            query = query.filter(AuditLogModel.source == source.strip())

        return query.order_by(
            AuditLogModel.created_at_in_seconds.desc(),
            AuditLogModel.id.desc(),
        ).first()

    def try_latest_event(self, **kwargs: Any) -> AuditLogModel | None:
        try:
            return self.latest_event(**kwargs)
        except Exception as exc:
            logger.warning(
                "audit_log_service: failed to query latest event category=%s event_type=%s error_type=%s",
                kwargs.get("category"),
                kwargs.get("event_type"),
                type(exc).__name__,
            )
            return None

    @staticmethod
    def _required_string(value: str, field_name: str) -> str:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
        raise ValueError(f"{field_name} must not be empty.")

    @staticmethod
    def _optional_string(value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        return None

    @classmethod
    def _stringify_identifier(cls, value: str | int | None) -> str | None:
        if value is None:
            return None
        return cls._optional_string(str(value))

    @staticmethod
    def _current_actor() -> dict[str, str | None]:
        user = getattr(g, "user", None) if has_request_context() else None
        if user is None:
            return {
                "actor_type": None,
                "actor_id": None,
                "actor_username": None,
            }
        actor_id = getattr(user, "id", None)
        actor_username = getattr(user, "username", None)
        return {
            "actor_type": "user",
            "actor_id": None if actor_id is None else str(actor_id).strip() or None,
            "actor_username": (
                actor_username.strip() if isinstance(actor_username, str) and actor_username.strip() else None
            ),
        }

    @staticmethod
    def _current_tenant_id() -> str | None:
        return current_tenant_id_or_none()

    @staticmethod
    def _current_request_id() -> str | None:
        if not has_request_context():
            return None
        return AuditLogService._optional_string(
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Request-Id")
            or getattr(g, "request_id", None)
        )

    @staticmethod
    def _current_correlation_id() -> str | None:
        if not has_request_context():
            return None
        return AuditLogService._optional_string(
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Correlation-Id")
            or getattr(g, "correlation_id", None)
        )


def get_audit_log_service() -> AuditLogService:
    return AuditLogService()
