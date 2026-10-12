"""Tenant-scoped connector profile CRUD. Ciphertext goes through ``secrets``."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from m8flow_backend.connectors.configuration import ConnectorConfigurationModel
from m8flow_backend.connectors.templates import (
    known_connector_type,
    plain_field_names,
    profile_fields,
    secret_field_names,
)
from m8flow_bpmn_core.errors import ServiceTaskExecutionError

from m8flow_backend.errors import ApiError
from m8flow_backend.secrets import add_secret, delete_secret, get_secret_value, update_secret

logger = logging.getLogger(__name__)

PROFILE_PARAMETER_NAME = "m8flow_profile"
# Applies to new profiles only: identifiers are immutable and BPMN files
# already reference older, looser ones, which keep resolving at runtime.
_PROFILE_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROFILE_NAME_MIN, PROFILE_NAME_MAX = 3, 50
_DISPLAY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.()-]*$")
DISPLAY_NAME_MIN, DISPLAY_NAME_MAX = 3, 60
DISPLAY_NAME_RULE = "Use letters, numbers, spaces, - _ . ( ). Must start with a letter or number."
PROFILE_NAME_RULE = (
    "Use lowercase letters, numbers and single hyphens, starting and ending "
    "with a letter or number."
)


def secret_ref(configuration_id: int, field_name: str) -> str:
    """Secret-store key for one profile field. Must match ``^\\w+$``."""
    return f"cnx_{configuration_id}_{field_name}"


def list_profiles(
    session: Session,
    *,
    tenant_id: str | None,
    connector_type: str | None = None,
    include_inactive: bool = True,
) -> list[ConnectorConfigurationModel]:
    # tenant_id None == "all tenants": caller-verified super-admin only
    # (auth.resolve_read_tenant_id).
    query = select(ConnectorConfigurationModel)
    if tenant_id is not None:
        query = query.where(ConnectorConfigurationModel.m8f_tenant_id == tenant_id)
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


def profile_detail(
    session: Session, profile: ConnectorConfigurationModel
) -> dict[str, Any]:
    """``to_dict`` plus the saved values of non-credential fields, so the edit
    form can prefill host, port, instance URL… Credentials never come back."""
    data = profile.to_dict()
    refs = profile.secret_refs or {}
    for name in sorted(plain_field_names(profile.connector_type)):
        key = refs.get(name)
        if key is None:
            continue
        value = get_secret_value(session, tenant_id=profile.m8f_tenant_id, key=key)
        if value is not None:
            data["config"][name] = value
    return data


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
    profile_name = (body.get("profile_name") or "").strip()
    # API callers may omit the display name; the identifier is a valid one.
    display_name = str(body.get("display_name") or profile_name).strip()
    errors = {
        key: message
        for key, message in (
            ("profile_name", _profile_name_error(profile_name)),
            ("display_name", _display_name_error(display_name)),
        )
        if message
    }
    if errors:
        raise _invalid(errors)
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
    if "display_name" in body:
        display_name = str(body["display_name"] or "").strip()
        message = _display_name_error(display_name)
        if message:
            raise _invalid({"display_name": message})
        profile.display_name = display_name
    if "description" in body:
        profile.description = body["description"] or None
    if "is_active" in body:
        profile.is_active = bool(body["is_active"])
    if "config" in body or "clear" in body:
        clear = body.get("clear") or []
        if not isinstance(clear, list) or not all(isinstance(n, str) for n in clear):
            raise ApiError(
                "validation_error", "'clear' must be a list of field names.", 400
            )
        _update_secrets(
            session,
            profile,
            tenant_id=tenant_id,
            submitted=dict(body.get("config") or {}),
            clear=clear,
            user_id=user_id,
        )
    # Secret-only edits do not touch this row's columns, so the timestamp
    # listener would not bump it; the profiles list shows it as Last updated.
    profile.updated_at = datetime.now(UTC)
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


def _profile_name_error(name: str) -> str | None:
    if not name:
        return "Identifier is required."
    if not PROFILE_NAME_MIN <= len(name) <= PROFILE_NAME_MAX:
        return f"Identifier must be {PROFILE_NAME_MIN}–{PROFILE_NAME_MAX} characters."
    if not _PROFILE_NAME_RE.fullmatch(name):
        return PROFILE_NAME_RULE
    return None


def _display_name_error(name: str) -> str | None:
    if not name:
        return "Display name is required."
    if not DISPLAY_NAME_MIN <= len(name) <= DISPLAY_NAME_MAX:
        return f"Display name must be {DISPLAY_NAME_MIN}–{DISPLAY_NAME_MAX} characters."
    if not _DISPLAY_NAME_RE.fullmatch(name):
        return DISPLAY_NAME_RULE
    return None


def _invalid(field_errors: dict[str, str]) -> ApiError:
    return ApiError(
        "validation_error",
        " ".join(field_errors.values()),
        400,
        field_errors=field_errors,
    )


def _name_conflict(profile_name: str, existing: ConnectorConfigurationModel | None) -> ApiError:
    if existing is not None and not existing.is_active:
        message = (
            f"An inactive '{profile_name}' profile already exists for this "
            "connector. Reactivate it, or delete it permanently, to reuse "
            "the name."
        )
    else:
        message = f"A '{profile_name}' profile already exists for this connector."
    return ApiError("profile_name_conflict", message, 409, field_errors={"profile_name": message})


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
    clear: list[str],
    user_id: int,
) -> None:
    fields = profile_fields(profile.connector_type)
    allowed = frozenset(fields)
    unknown = [name for name in [*submitted, *clear] if name not in allowed]
    if unknown:
        raise ApiError(
            "validation_error",
            f"Unknown profile fields: {', '.join(sorted(set(unknown)))}.",
            400,
        )
    required = [name for name in clear if fields[name].get("required")]
    if required:
        raise ApiError(
            "validation_error",
            f"Required fields cannot be cleared: {', '.join(sorted(set(required)))}.",
            400,
        )
    both = [name for name in clear if submitted.get(name) not in (None, "")]
    if both:
        raise ApiError(
            "validation_error",
            f"Fields cannot be both set and cleared: {', '.join(sorted(set(both)))}.",
            400,
        )
    refs = dict(profile.secret_refs or {})
    for name in clear:
        key = refs.pop(name, None)
        if key is None:
            continue
        try:
            delete_secret(session, tenant_id=tenant_id, key=key)
        except ApiError:
            # Already gone from the store; dropping the ref is what matters.
            logger.warning("Could not delete cleared secret %s", key, exc_info=True)
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
