"""Tenant-scoped connector profile CRUD. Ciphertext goes through ``secrets``."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from m8flow_backend.connectors.configuration import ConnectorConfigurationModel
from m8flow_backend.connectors.templates import known_connector_type, secret_field_names
from m8flow_bpmn_core.errors import ServiceTaskExecutionError

from m8flow_backend.errors import ApiError
from m8flow_backend.secrets import add_secret, delete_secret, get_secret_value, update_secret

logger = logging.getLogger(__name__)

PROFILE_PARAMETER_NAME = "m8flow_profile"
_PROFILE_NAME_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}[a-zA-Z0-9]$|^[a-zA-Z0-9]$"
)


def secret_ref(configuration_id: int, field_name: str) -> str:
    """Secret-store key for one profile field. Must match ``^\\w+$``."""
    return f"cnx_{configuration_id}_{field_name}"


def list_profiles(
    session: Session,
    *,
    tenant_id: str,
    connector_type: str | None = None,
    include_inactive: bool = True,
) -> list[ConnectorConfigurationModel]:
    query = select(ConnectorConfigurationModel).where(
        ConnectorConfigurationModel.m8f_tenant_id == tenant_id
    )
    if connector_type:
        query = query.where(ConnectorConfigurationModel.connector_type == connector_type)
    if not include_inactive:
        query = query.where(ConnectorConfigurationModel.is_active.is_(True))
    query = query.order_by(
        ConnectorConfigurationModel.connector_type,
        ConnectorConfigurationModel.profile_name,
    )
    return list(session.scalars(query).all())


def get_profile(
    session: Session, *, tenant_id: str, profile_id: int
) -> ConnectorConfigurationModel:
    profile = session.scalars(
        select(ConnectorConfigurationModel).where(
            ConnectorConfigurationModel.m8f_tenant_id == tenant_id,
            ConnectorConfigurationModel.id == profile_id,
        )
    ).first()
    if profile is None:
        raise ApiError("not_found", "Connector profile not found.", 404)
    return profile


def create_profile(
    session: Session,
    *,
    tenant_id: str,
    body: dict[str, Any],
    user_id: int,
) -> ConnectorConfigurationModel:
    connector_type = (body.get("connector_type") or "").strip()
    if not known_connector_type(connector_type):
        raise ApiError(
            "not_found", f"Unknown connector type '{connector_type}'.", 404
        )
    profile_name = _validated_profile_name(body.get("profile_name"))
    display_name = (body.get("display_name") or profile_name).strip()
    secrets_in = _secret_values_from_config(connector_type, body.get("config") or {})

    existing = _by_name(session, tenant_id, connector_type, profile_name)
    if existing is not None:
        raise _name_conflict(profile_name, existing)

    profile = ConnectorConfigurationModel(
        m8f_tenant_id=tenant_id,
        connector_type=connector_type,
        profile_name=profile_name,
        display_name=display_name,
        description=(body.get("description") or None),
        config_json={},
        secret_refs={},
        is_active=True,
        created_by_user_id=user_id,
    )
    session.add(profile)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        existing = _by_name(session, tenant_id, connector_type, profile_name)
        raise _name_conflict(profile_name, existing) from exc

    try:
        profile.secret_refs = _write_secrets(
            session,
            tenant_id=tenant_id,
            configuration_id=profile.id,
            secret_values=secrets_in,
            user_id=user_id,
        )
        session.flush()
    except Exception:
        session.rollback()
        raise
    return profile


def update_profile(
    session: Session,
    *,
    tenant_id: str,
    profile_id: int,
    body: dict[str, Any],
    user_id: int,
) -> ConnectorConfigurationModel:
    profile = get_profile(session, tenant_id=tenant_id, profile_id=profile_id)
    if body.get("display_name"):
        profile.display_name = str(body["display_name"]).strip()
    if "description" in body:
        profile.description = body["description"] or None
    if "is_active" in body:
        profile.is_active = bool(body["is_active"])
    if "config" in body:
        _update_secrets(
            session,
            profile,
            tenant_id=tenant_id,
            submitted=dict(body.get("config") or {}),
            user_id=user_id,
        )
    session.flush()
    return profile


def resolve_for_runtime(
    session: Session,
    *,
    tenant_id: str,
    connector_type: str,
    profile_name: str,
) -> dict[str, Any]:
    """Plain config plus decrypted secrets for one active profile.

    Missing or inactive profiles fail closed so execute never posts empty
    credentials. Decrypted values exist only for the duration of the call.
    """
    profile = _by_name(session, tenant_id, connector_type, profile_name)
    if profile is None:
        raise ServiceTaskExecutionError(
            f"No '{profile_name}' profile is configured for connector "
            f"'{connector_type}'."
        )
    if not profile.is_active:
        raise ServiceTaskExecutionError(
            f"Connector profile '{profile_name}' is inactive. Reactivate it "
            "under Connectors, or pick another profile on this task."
        )
    resolved: dict[str, Any] = dict(profile.config_json or {})
    for name, key in (profile.secret_refs or {}).items():
        value = get_secret_value(session, tenant_id=tenant_id, key=key)
        if value is None:
            raise ServiceTaskExecutionError(
                f"Profile '{profile_name}' is missing its stored value for "
                f"'{name}'. Re-enter it under Connectors."
            )
        resolved[name] = value
    return resolved


def deactivate_profile(
    session: Session, *, tenant_id: str, profile_id: int
) -> ConnectorConfigurationModel:
    profile = get_profile(session, tenant_id=tenant_id, profile_id=profile_id)
    profile.is_active = False
    session.flush()
    return profile


def delete_profile(session: Session, *, tenant_id: str, profile_id: int) -> None:
    profile = get_profile(session, tenant_id=tenant_id, profile_id=profile_id)
    refs = list((profile.secret_refs or {}).values())
    session.delete(profile)
    session.flush()
    for key in refs:
        try:
            delete_secret(session, tenant_id=tenant_id, key=key)
        except ApiError:
            logger.warning(
                "Could not delete secret for removed profile %s",
                profile_id,
                exc_info=True,
            )


def _by_name(
    session: Session, tenant_id: str, connector_type: str, profile_name: str
) -> ConnectorConfigurationModel | None:
    return session.scalars(
        select(ConnectorConfigurationModel).where(
            ConnectorConfigurationModel.m8f_tenant_id == tenant_id,
            ConnectorConfigurationModel.connector_type == connector_type,
            ConnectorConfigurationModel.profile_name == profile_name,
        )
    ).first()


def _validated_profile_name(raw: Any) -> str:
    name = (raw or "").strip()
    if not _PROFILE_NAME_RE.match(name):
        raise ApiError(
            "validation_error",
            "Profile name must be 1-64 characters of letters, digits, '.', "
            "'-' or '_', starting and ending with a letter or digit.",
            400,
        )
    return name


def _name_conflict(profile_name: str, existing: ConnectorConfigurationModel | None) -> ApiError:
    if existing is not None and not existing.is_active:
        message = (
            f"An inactive '{profile_name}' profile already exists for this "
            "connector. Reactivate it, or delete it permanently, to reuse "
            "the name."
        )
    else:
        message = f"A '{profile_name}' profile already exists for this connector."
    return ApiError("profile_name_conflict", message, 409)


def _secret_values_from_config(connector_type: str, submitted: dict[str, Any]) -> dict[str, str]:
    allowed = secret_field_names(connector_type)
    unknown = [name for name in submitted if name not in allowed]
    if unknown:
        raise ApiError(
            "validation_error",
            f"Unknown profile fields: {', '.join(sorted(unknown))}.",
            400,
        )
    values: dict[str, str] = {}
    for name in allowed:
        raw = submitted.get(name)
        if raw in (None, ""):
            continue
        values[name] = str(raw)
    return values


def _write_secrets(
    session: Session,
    *,
    tenant_id: str,
    configuration_id: int,
    secret_values: dict[str, str],
    user_id: int,
) -> dict[str, str]:
    refs: dict[str, str] = {}
    written: list[str] = []
    try:
        for name, value in secret_values.items():
            key = secret_ref(configuration_id, name)
            add_secret(session, tenant_id=tenant_id, key=key, value=value, user_id=user_id)
            refs[name] = key
            written.append(key)
    except ApiError:
        for key in written:
            try:
                delete_secret(session, tenant_id=tenant_id, key=key)
            except Exception:
                logger.warning("Compensating secret delete failed", exc_info=True)
        raise
    except Exception as exc:
        for key in written:
            try:
                delete_secret(session, tenant_id=tenant_id, key=key)
            except Exception:
                logger.warning("Compensating secret delete failed", exc_info=True)
        raise ApiError(
            "connector_profile_error",
            "Could not store the profile's credentials.",
            500,
        ) from exc
    return refs


def _update_secrets(
    session: Session,
    profile: ConnectorConfigurationModel,
    *,
    tenant_id: str,
    submitted: dict[str, Any],
    user_id: int,
) -> None:
    allowed = secret_field_names(profile.connector_type)
    unknown = [name for name in submitted if name not in allowed]
    if unknown:
        raise ApiError(
            "validation_error",
            f"Unknown profile fields: {', '.join(sorted(unknown))}.",
            400,
        )
    refs = dict(profile.secret_refs or {})
    for name in allowed:
        raw = submitted.get(name)
        if raw in (None, ""):
            continue
        key = refs.get(name) or secret_ref(profile.id, name)
        if name in refs:
            update_secret(session, tenant_id=tenant_id, key=key, value=str(raw))
        else:
            add_secret(
                session, tenant_id=tenant_id, key=key, value=str(raw), user_id=user_id
            )
            refs[name] = key
    profile.secret_refs = refs
