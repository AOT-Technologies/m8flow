"""Tenant-scoped named configuration variables."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from m8flow_backend.errors import ApiError
from m8flow_backend.models.named_value import NamedValueModel
from m8flow_backend.secrets import (
    add_secret,
    delete_configuration_value,
    delete_secret,
    set_configuration_value,
    update_secret,
)

LOGGER = logging.getLogger(__name__)
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
_CLEANUP_KEY = "m8flow_named_value_secret_cleanup"


@event.listens_for(Session, "after_commit")
def _cleanup_after_commit(session: Session) -> None:
    pending = session.info.pop(_CLEANUP_KEY, [])
    if not pending:
        return
    from m8flow_backend.db import session_scope

    for tenant_id, variable_id, provider_key in pending:
        try:
            with session_scope() as cleanup_session:
                if cleanup_session.bind and cleanup_session.bind.dialect.name == "postgresql":
                    cleanup_session.execute(
                        text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
                        {"tenant_id": tenant_id},
                    )
                if provider_key == variable_id:
                    delete_configuration_value(
                        cleanup_session,
                        tenant_id=tenant_id,
                        variable_id=variable_id,
                    )
                else:
                    delete_secret(cleanup_session, tenant_id=tenant_id, key=provider_key)
        except ApiError as exc:
            if exc.status_code != 404:
                LOGGER.warning(
                    "Could not clean up retired secret for named value %s",
                    variable_id,
                    exc_info=True,
                )
        except Exception:
            LOGGER.warning(
                "Could not clean up retired secret for named value %s",
                variable_id,
                exc_info=True,
            )


@event.listens_for(Session, "after_rollback")
def _discard_pending_cleanup(session: Session) -> None:
    session.info.pop(_CLEANUP_KEY, None)


def list_named_values(session: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(NamedValueModel)
        .where(NamedValueModel.m8f_tenant_id == tenant_id)
        .order_by(func.lower(NamedValueModel.name), NamedValueModel.id)
    ).all()
    return [_serialize(row) for row in rows]


def get_named_value(session: Session, *, tenant_id: str, variable_id: str) -> dict[str, Any]:
    return _serialize(_get_row(session, tenant_id=tenant_id, variable_id=variable_id))


def create_named_value(
    session: Session,
    *,
    tenant_id: str,
    body: dict[str, Any],
    user_id: int,
) -> dict[str, Any]:
    name = _validated_name(body.get("name"))
    description = _description(body.get("description"))
    sensitive = body.get("is_sensitive", False)
    if not isinstance(sensitive, bool):
        raise ApiError("validation_error", "is_sensitive must be a boolean.", 400)
    _ensure_name_available(session, tenant_id=tenant_id, name=name)
    if "value" not in body or body["value"] is None or body["value"] == "":
        raise ApiError("validation_error", "A non-empty value is required.", 400)

    variable_id = str(uuid.uuid4())
    row = NamedValueModel(
        id=variable_id,
        m8f_tenant_id=tenant_id,
        name=name,
        description=description,
        is_sensitive=sensitive,
        value=None if sensitive else body["value"],
        is_configured=True,
        provider_key=variable_id if sensitive else None,
        created_by_user_id=user_id,
    )
    if sensitive:
        _require_secret_string(body["value"])
        set_configuration_value(
            session,
            tenant_id=tenant_id,
            variable_id=variable_id,
            value=body["value"],
            user_id=user_id,
        )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        _cleanup_failed_create(session, row)
        raise _name_conflict(name) from exc
    return _serialize(row)


def update_named_value(
    session: Session,
    *,
    tenant_id: str,
    variable_id: str,
    body: dict[str, Any],
    user_id: int,
) -> dict[str, Any]:
    row = _get_row(session, tenant_id=tenant_id, variable_id=variable_id)
    if "name" in body:
        updated_name = _validated_name(body["name"])
        if updated_name.casefold() != row.name.casefold():
            _ensure_name_available(
                session,
                tenant_id=tenant_id,
                name=updated_name,
                except_id=row.id,
            )
        row.name = updated_name
    if "description" in body:
        row.description = _description(body["description"])

    target_sensitive = body.get("is_sensitive", row.is_sensitive)
    if not isinstance(target_sensitive, bool):
        raise ApiError("validation_error", "is_sensitive must be a boolean.", 400)
    has_value = "value" in body and body["value"] not in (None, "")

    if target_sensitive:
        if not row.is_sensitive:
            if not has_value:
                raise ApiError(
                    "validation_error",
                    "Supply a new value when changing a variable to sensitive.",
                    400,
                )
            _require_secret_string(body["value"])
            row.value = None
            row.provider_key = row.id
            row.is_configured = True
            set_configuration_value(
                session,
                tenant_id=tenant_id,
                variable_id=row.id,
                value=body["value"],
                user_id=user_id,
            )
        elif has_value:
            _require_secret_string(body["value"])
            _write_existing_sensitive(
                session,
                row,
                tenant_id=tenant_id,
                value=body["value"],
                user_id=user_id,
            )
            row.is_configured = True
        row.is_sensitive = True
    else:
        if row.is_sensitive:
            if not has_value:
                raise ApiError(
                    "validation_error",
                    "Supply a new value when changing a variable to non-sensitive.",
                    400,
                )
            old_key = row.provider_key
            row.value = body["value"]
            row.provider_key = None
            row.is_configured = True
            if old_key:
                _schedule_cleanup(session, tenant_id, row.id, old_key)
        elif has_value:
            row.value = body["value"]
            row.is_configured = True
        row.is_sensitive = False

    try:
        session.flush()
    except IntegrityError as exc:
        name = row.name
        session.rollback()
        raise _name_conflict(name) from exc
    return _serialize(row)


def delete_named_value(session: Session, *, tenant_id: str, variable_id: str) -> None:
    row = _get_row(session, tenant_id=tenant_id, variable_id=variable_id)
    if row.is_sensitive and row.provider_key:
        _schedule_cleanup(session, tenant_id, row.id, row.provider_key)
    session.delete(row)
    session.flush()


def _write_existing_sensitive(
    session: Session,
    row: NamedValueModel,
    *,
    tenant_id: str,
    value: str,
    user_id: int,
) -> None:
    if row.provider_key == row.id:
        set_configuration_value(
            session,
            tenant_id=tenant_id,
            variable_id=row.id,
            value=value,
            user_id=user_id,
        )
        return

    # Rows backfilled from the legacy table or Vault path keep using their old
    # key until a separately verified path migration changes the pointer.
    if not row.provider_key:
        set_configuration_value(
            session,
            tenant_id=tenant_id,
            variable_id=row.id,
            value=value,
            user_id=user_id,
        )
        row.provider_key = row.id
        return
    try:
        update_secret(session, tenant_id=tenant_id, key=row.provider_key, value=value)
    except ApiError as exc:
        if exc.status_code != 404:
            raise
        add_secret(
            session,
            tenant_id=tenant_id,
            key=row.provider_key,
            value=value,
            user_id=user_id,
        )


def _schedule_cleanup(session: Session, tenant_id: str, variable_id: str, provider_key: str) -> None:
    session.info.setdefault(_CLEANUP_KEY, []).append((tenant_id, variable_id, provider_key))


def _cleanup_failed_create(session: Session, row: NamedValueModel) -> None:
    tenant_id = row.m8f_tenant_id
    variable_id = row.id
    sensitive = row.is_sensitive
    session.rollback()
    if sensitive:
        try:
            delete_configuration_value(
                session,
                tenant_id=tenant_id,
                variable_id=variable_id,
            )
        except Exception:
            LOGGER.warning("Could not clean up failed named-value write", exc_info=True)


def _get_row(session: Session, *, tenant_id: str, variable_id: str) -> NamedValueModel:
    try:
        parsed_id = str(uuid.UUID(variable_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ApiError("not_found", "Configuration variable not found.", 404) from exc
    row = session.scalar(
        select(NamedValueModel).where(
            NamedValueModel.id == parsed_id,
            NamedValueModel.m8f_tenant_id == tenant_id,
        )
    )
    if row is None:
        raise ApiError("not_found", "Configuration variable not found.", 404)
    return row


def _ensure_name_available(
    session: Session,
    *,
    tenant_id: str,
    name: str,
    except_id: str | None = None,
) -> None:
    statement = select(NamedValueModel.id).where(
        NamedValueModel.m8f_tenant_id == tenant_id,
        func.lower(NamedValueModel.name) == name.casefold(),
    )
    if except_id is not None:
        statement = statement.where(NamedValueModel.id != except_id)
    if session.scalar(statement) is not None:
        raise _name_conflict(name)


def _serialize(row: NamedValueModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenantId": row.m8f_tenant_id,
        "name": row.name,
        "description": row.description,
        "isSensitive": row.is_sensitive,
        "isConfigured": row.is_configured,
        "value": None if row.is_sensitive else row.value,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validated_name(value: Any) -> str:
    if not isinstance(value, str):
        raise ApiError("validation_error", "name must be a string.", 400)
    name = value.strip()
    if not _NAME.fullmatch(name):
        raise ApiError(
            "validation_error",
            "Name must be 1-255 characters using letters, numbers, underscores, or hyphens.",
            400,
        )
    return name


def _description(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError("validation_error", "description must be a string or null.", 400)
    return value.strip() or None


def _require_secret_string(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError("validation_error", "Sensitive values must be non-empty strings.", 400)
    return value


def _name_conflict(name: str) -> ApiError:
    return ApiError(
        "configuration_variable_conflict",
        f"A configuration variable named '{name}' already exists in this tenant.",
        409,
    )
