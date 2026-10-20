"""Tenant-scoped connector profile CRUD. Ciphertext goes through ``secrets``."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from m8flow_backend.connectors.configuration import ConnectorConfigurationModel
from m8flow_backend.connectors.templates import known_connector_type, secret_field_names, template_for
from m8flow_bpmn_core.errors import ServiceTaskExecutionError

from m8flow_backend.errors import ApiError
from m8flow_backend.secrets import add_secret, delete_secret, get_secret_value, update_secret

logger = logging.getLogger(__name__)

PROFILE_PARAMETER_NAME = "m8flow_profile"
# 3-50 chars. Only enforced on create: identifiers are immutable afterwards.
# Used with .fullmatch(); anchored too so a future .match()/.search() caller
# can't be fooled by a valid prefix/suffix around invalid characters.
_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,48}[a-zA-Z0-9]$")
# Starts with a letter/digit; then letters, digits, space, _ . ( ) -.
_DISPLAY_NAME_RE = re.compile(r"^[^\W_][\w .()-]*$")
DISPLAY_NAME_HINT = "Use letters, numbers, spaces, - _ . ( ). Must start with a letter or number."


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
    profile_name = str(body.get("profile_name") or "").strip()
    display_name = str(body.get("display_name") or profile_name).strip()
    _raise_field_errors(
        profile_name=_profile_name_error(profile_name),
        display_name=_display_name_error(display_name),
    )
    secrets_in = _secret_values_from_config(connector_type, _config_from_body(body))

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
        # Names saved before the rules existed keep working until renamed.
        if display_name != profile.display_name:
            _raise_field_errors(display_name=_display_name_error(display_name))
            profile.display_name = display_name
    if "description" in body:
        profile.description = body["description"] or None
    if "is_active" in body:
        profile.is_active = bool(body["is_active"])
    clear = body.get("clear") or []
    if (
        not isinstance(clear, list)
        or not all(isinstance(name, str) for name in clear)
        or len(set(clear)) != len(clear)
    ):
        raise ApiError("validation_error", "clear must be a list of unique field ids.", 400)
    if "config" in body or clear:
        _update_secrets(
            session,
            profile,
            tenant_id=tenant_id,
            submitted=_config_from_body(body),
            clear=clear,
            user_id=user_id,
        )
    session.flush()
    return profile


def plain_values(session: Session, profile: ConnectorConfigurationModel) -> dict[str, str]:
    """Decrypted values of the fields the template marks ``isPrefillSafe``
    (host, port, username...) so the edit form can prefill them. Credentials
    stay out."""
    refs = profile.secret_refs or {}
    template = template_for(profile.connector_type) or {}
    values: dict[str, str] = {}
    for field in template.get("profileFields", []):
        name = field.get("id")
        if not isinstance(name, str) or not name:
            continue  # malformed template field: never coerce into a secret_refs key
        # Deny by default: a field must opt in. Highly sensitive and
        # password-typed fields are withheld even then, so one wrong flag on a
        # template can't leak a credential.
        if (
            field.get("isPrefillSafe") is not True
            or field.get("isHighlySensitive", True)
            or field.get("type") == "password"
            or name not in refs
        ):
            continue
        value = get_secret_value(session, tenant_id=profile.m8f_tenant_id, key=refs[name])
        if value is not None:
            values[name] = value
    return values


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
    if _PROFILE_NAME_RE.fullmatch(name):
        return None
    return (
        "Identifier must be 3-50 characters of letters, digits, '.', '-' or "
        "'_', starting and ending with a letter or digit."
    )


def _display_name_error(name: str) -> str | None:
    if not name:
        return "Display name is required."
    if not 3 <= len(name) <= 60:
        return "Display name must be 3-60 characters."
    if not _DISPLAY_NAME_RE.fullmatch(name):
        return DISPLAY_NAME_HINT
    return None


def _raise_field_errors(**messages: str | None) -> None:
    errors = {field: message for field, message in messages.items() if message}
    if errors:
        raise ApiError("validation_error", " ".join(errors.values()), 400, errors=errors)


def _name_conflict(profile_name: str, existing: ConnectorConfigurationModel | None) -> ApiError:
    if existing is not None and not existing.is_active:
        message = (
            f"An inactive '{profile_name}' profile already exists for this "
            "connector. Reactivate it, or delete it permanently, to reuse "
            "the name."
        )
    else:
        message = f"A '{profile_name}' profile already exists for this connector."
    return ApiError("profile_name_conflict", message, 409, errors={"profile_name": message})


def _config_from_body(body: dict[str, Any]) -> dict[str, Any]:
    config = body.get("config") or {}
    if not isinstance(config, dict):
        raise ApiError("validation_error", "config must be an object of field values.", 400)
    return dict(config)


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
        # Numbers (a port) are fine; str() of a bool, list or object never is.
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise ApiError("validation_error", f"{name} must be a text value.", 400)
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
    # One parse for both the set/clear conflict check and the write loop.
    secret_values = _secret_values_from_config(profile.connector_type, submitted)
    allowed = secret_field_names(profile.connector_type)
    unknown = sorted({name for name in clear if name not in allowed})
    if unknown:
        raise ApiError(
            "validation_error", f"Unknown profile fields: {', '.join(unknown)}.", 400
        )
    # Keyed by str(id) to match secret_field_names(); a field allowed there but
    # missing here (template/plugin drift) is a 400, never a KeyError -> 500.
    fields = {
        str(field["id"]): field
        for field in (template_for(profile.connector_type) or {}).get("profileFields", [])
    }
    missing = sorted({name for name in clear if name not in fields})
    if missing:
        raise ApiError(
            "validation_error", f"Unknown profile fields: {', '.join(missing)}.", 400
        )
    for name in clear:
        meta = fields[name]
        label = meta.get("label", name)
        if meta.get("required"):
            raise ApiError(
                "validation_error", f"{label} is required and cannot be cleared.", 400
            )
        if name in secret_values:
            raise ApiError(
                "validation_error", f"{label} cannot be both set and cleared.", 400
            )
    refs = dict(profile.secret_refs or {})
    # Writes before deletes: a failed write then leaves nothing removed from an
    # external store (Vault) that the DB rollback can't restore. A ref whose
    # secret is already gone (deleted via the Secrets API) is re-added on set
    # and skipped on clear, so the profile stays fixable from the form.
    for name, value in secret_values.items():
        key = refs.get(name) or secret_ref(profile.id, name)
        if name in refs and _ignore_missing(update_secret, session, tenant_id=tenant_id, key=key, value=value):
            continue
        add_secret(session, tenant_id=tenant_id, key=key, value=value, user_id=user_id)
        refs[name] = key
    for name in clear:
        key = refs.pop(name, None)
        if key is not None:
            _ignore_missing(delete_secret, session, tenant_id=tenant_id, key=key)
    profile.secret_refs = refs


def _ignore_missing(op: Any, session: Session, **kwargs: Any) -> bool:
    """Run a secret op; False instead of the provider's 404 when the key is gone."""
    try:
        op(session, **kwargs)
    except ApiError as exc:
        if exc.status_code != 404:
            raise
        return False
    return True
