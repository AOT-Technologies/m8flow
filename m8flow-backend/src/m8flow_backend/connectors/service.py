"""Tenant-scoped connector profile CRUD. Ciphertext goes through ``secrets``."""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from m8flow_backend.connectors.configuration import (
    ConnectorConfigurationModel,
    ConnectorVariableModel,
)
from m8flow_backend.connectors.templates import known_connector_type, secret_field_names, template_for
from m8flow_core.errors import ServiceTaskExecutionError

from m8flow_backend.db import session_scope
from m8flow_backend.errors import ApiError
from m8flow_backend.secrets import (
    delete_connector_configuration,
    delete_secret,
    get_connector_configuration,
    get_secret_value,
    set_connector_configuration,
)

logger = logging.getLogger(__name__)

PROFILE_PARAMETER_NAME = "m8flow_profile"
# 3-50 chars. Only enforced on create: identifiers are immutable afterwards.
# Used with .fullmatch(); anchored too so a future .match()/.search() caller
# can't be fooled by a valid prefix/suffix around invalid characters.
_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,48}[a-zA-Z0-9]$")
# Starts with a letter/digit; then letters, digits, space, _ . ( ) -.
_DISPLAY_NAME_RE = re.compile(r"^[^\W_][\w .()-]*$")
DISPLAY_NAME_HINT = "Use letters, numbers, spaces, - _ . ( ). Must start with a letter or number."
_RETIRED_SECRET_CLEANUP_KEY = "m8flow_connector_retired_secret_cleanup"
_STAGED_SECRET_CLEANUP_KEY = "m8flow_connector_staged_secret_cleanup"
_CLEANUP_LISTENERS_REGISTERED_ATTR = "_m8flow_connector_cleanup_listeners_registered"


def _cleanup_retired_connector_secrets_after_commit(session: Session) -> None:
    # New secret documents are now referenced by committed profile rows. Retire
    # their predecessors only after that reference change is durable.
    session.info.pop(_STAGED_SECRET_CLEANUP_KEY, None)
    _run_connector_secret_cleanup(
        session.info.pop(_RETIRED_SECRET_CLEANUP_KEY, set()),
        message="Could not clean up retired connector secret",
    )


def _cleanup_staged_connector_secrets_after_rollback(session: Session) -> None:
    # A failed transaction must leave the old secret untouched and remove the
    # newly written document, which the rolled-back profile no longer points to.
    session.info.pop(_RETIRED_SECRET_CLEANUP_KEY, None)
    _run_connector_secret_cleanup(
        session.info.pop(_STAGED_SECRET_CLEANUP_KEY, set()),
        message="Could not clean up staged connector secret after rollback",
    )


def _register_connector_secret_cleanup_listeners() -> None:
    """Register cleanup hooks once, including across module reloads.

    These events target SQLAlchemy's global ``Session`` class, so ordinary
    module-level decorators can accumulate duplicate listeners when a reload
    based dev/test runner imports this module again.
    """
    if getattr(Session, _CLEANUP_LISTENERS_REGISTERED_ATTR, False):
        return
    event.listen(Session, "after_commit", _cleanup_retired_connector_secrets_after_commit)
    event.listen(Session, "after_rollback", _cleanup_staged_connector_secrets_after_rollback)
    setattr(Session, _CLEANUP_LISTENERS_REGISTERED_ATTR, True)


_register_connector_secret_cleanup_listeners()


def _run_connector_secret_cleanup(
    pending: set[tuple[str, str, str]], *, message: str
) -> None:
    if not pending:
        return
    for tenant_id, kind, key in pending:
        try:
            with session_scope() as cleanup_session:
                if cleanup_session.bind and cleanup_session.bind.dialect.name == "postgresql":
                    cleanup_session.execute(
                        text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
                        {"tenant_id": tenant_id},
                    )
                if kind == "document":
                    delete_connector_configuration(
                        cleanup_session, tenant_id=tenant_id, configuration_id=key
                    )
                else:
                    delete_secret(cleanup_session, tenant_id=tenant_id, key=key)
        except ApiError as exc:
            if exc.status_code != 404:
                logger.warning("%s for profile key %s", message, key, exc_info=True)
        except Exception:
            logger.warning("%s for profile key %s", message, key, exc_info=True)


def _schedule_connector_secret_cleanup(
    session: Session, *, tenant_id: str, kind: str, key: str, staged: bool = False
) -> None:
    cleanup_key = _STAGED_SECRET_CLEANUP_KEY if staged else _RETIRED_SECRET_CLEANUP_KEY
    session.info.setdefault(cleanup_key, set()).add((tenant_id, kind, str(key)))


def secret_ref(configuration_id: int, field_name: str) -> str:
    """Legacy secret-store key for a field in profiles written before UUID docs."""
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
    query = select(ConnectorConfigurationModel).options(
        selectinload(ConnectorConfigurationModel.variables)
    )
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
    plain_values, sensitive_values = _split_profile_values(
        connector_type, _config_from_body(body)
    )

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
        # Profiles without sensitive fields have no provider document and must
        # remain usable when the secret provider is unavailable.
        provider_key=str(uuid4()) if sensitive_values else None,
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
        profile.secret_refs = {
            name: profile.provider_key for name in sensitive_values
        }
        _sync_profile_secret_document(
            session,
            profile,
            values=sensitive_values,
            user_id=user_id,
            old_provider_key=None,
            old_refs={},
        )
        _sync_connector_variables(
            session,
            profile,
            plain_values=plain_values,
            verified_secret_fields=set(sensitive_values),
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
        old_provider_key = profile.provider_key
        old_refs = _profile_secret_refs(session, profile)
        submitted_config = _config_from_body(body)
        _submitted_plain, submitted_sensitive = _split_profile_values(
            profile.connector_type, submitted_config
        )
        sensitive_names = secret_field_names(profile.connector_type)
        sensitive_changed = bool(submitted_sensitive or (set(clear) & sensitive_names))
        plain_values, sensitive_values = _update_profile_values(
            session,
            profile,
            submitted=submitted_config,
            clear=clear,
        )
        needs_secret_sync = (
            sensitive_changed
            or bool(old_provider_key and not _is_uuid_key(old_provider_key))
            or any(key != old_provider_key for key in old_refs.values())
            or (bool(sensitive_values) and not old_provider_key)
        )
        if needs_secret_sync:
            # Never overwrite the currently referenced Vault document in place
            # when its sensitive contents change. The database can switch to
            # the new key atomically, and rollback can discard the staged key.
            if sensitive_values:
                profile.provider_key = str(uuid4())
            elif not _is_uuid_key(profile.provider_key):
                profile.provider_key = str(uuid4())
            profile.secret_refs = {
                name: profile.provider_key for name in sensitive_values
            }
            _sync_profile_secret_document(
                session,
                profile,
                values=sensitive_values,
                user_id=user_id,
                old_provider_key=old_provider_key,
                old_refs=old_refs,
            )
        _sync_connector_variables(
            session,
            profile,
            plain_values=plain_values,
            verified_secret_fields=set(sensitive_values),
        )
    session.flush()
    return profile


def plain_values(session: Session, profile: ConnectorConfigurationModel) -> dict[str, Any]:
    """Decrypted values of the fields the template marks ``isPrefillSafe``
    (host, port, username...) so the edit form can prefill them. Credentials
    stay out."""
    rows = (
        {row.field_name: row for row in _profile_variable_rows(session, profile)}
        if session is not None and getattr(profile, "id", None) is not None
        else {}
    )
    sensitive_names = secret_field_names(profile.connector_type)
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
            or name in sensitive_names
        ):
            continue
        row = rows.get(name)
        value = row.value if row is not None and not row.is_sensitive else None
        # A legacy profile may still have this now-ordinary setting only in
        # its old field secret/document. It is safe to prefill because the
        # current descriptor explicitly classifies it as non-sensitive.
        if value is None:
            value = _legacy_profile_value(session, profile, name)
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
    for row in _profile_variable_rows(session, profile):
        if row.is_sensitive:
            continue
        if row.value is not None:
            resolved[row.field_name] = row.value
    refs = _profile_secret_refs(session, profile)
    sensitive_names = secret_field_names(profile.connector_type)
    document = None
    document_references = {
        name for name, key in refs.items() if key == profile.provider_key
    }
    sensitive_document_references = document_references & sensitive_names
    if profile.provider_key and document_references:
        document = get_connector_configuration(
            session,
            tenant_id=tenant_id,
            configuration_id=profile.provider_key,
        )
        if document is None and sensitive_document_references:
            raise ServiceTaskExecutionError(
                f"Profile '{profile_name}' is missing its stored credentials. Re-enter them under Connectors."
            )
    for name, key in refs.items():
        if name in sensitive_names:
            if key == profile.provider_key:
                value = document.get(name) if document is not None else None
            else:
                value = get_secret_value(session, tenant_id=tenant_id, key=key)
        else:
            value = _legacy_profile_value(session, profile, name)
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
    provider_key = profile.provider_key
    session.delete(profile)
    session.flush()
    for key in refs:
        if key == provider_key:
            continue
        _schedule_connector_secret_cleanup(
            session, tenant_id=tenant_id, kind="secret", key=key
        )
    if provider_key:
        _schedule_connector_secret_cleanup(
            session, tenant_id=tenant_id, kind="document", key=provider_key
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


def _profile_variable_rows(
    session: Session,
    profile: ConnectorConfigurationModel,
) -> list[ConnectorVariableModel]:
    return list(
        session.scalars(
            select(ConnectorVariableModel).where(
                ConnectorVariableModel.m8f_tenant_id == profile.m8f_tenant_id,
                ConnectorVariableModel.connector_configuration_id == profile.id,
            )
        ).all()
    )


def _profile_secret_refs(
    session: Session,
    profile: ConnectorConfigurationModel,
) -> dict[str, str]:
    refs = dict(profile.secret_refs or {})
    for row in _profile_variable_rows(session, profile):
        if row.is_sensitive and row.provider_key:
            refs[row.field_name] = row.provider_key
    return refs


def _sync_connector_variables(
    session: Session,
    profile: ConnectorConfigurationModel,
    *,
    plain_values: dict[str, Any],
    verified_secret_fields: set[str],
) -> None:
    """Persist ordinary fields in SQL and only sensitive refs in metadata."""
    plain = dict(plain_values)
    refs = dict(profile.secret_refs or {})
    overlap = sorted(set(plain) & set(refs))
    if overlap:
        raise ApiError(
            "connector_profile_error",
            "A connector field cannot be both ordinary and sensitive.",
            400,
            errors={"fields": overlap},
        )

    existing = {row.field_name: row for row in _profile_variable_rows(session, profile)}
    desired = set(plain) | set(refs)
    synced: list[ConnectorVariableModel] = []
    for field_name in desired:
        variable = existing.pop(field_name, None)
        previously_configured = variable.is_configured if variable is not None else False
        if variable is None:
            variable = ConnectorVariableModel(
                m8f_tenant_id=profile.m8f_tenant_id,
                connector_configuration_id=profile.id,
                field_name=field_name,
            )
            session.add(variable)
        variable.created_by_user_id = profile.created_by_user_id
        if field_name in refs:
            provider_key = refs[field_name]
            variable.is_sensitive = True
            variable.provider_key = provider_key
            variable.value = None
            variable.is_configured = field_name in verified_secret_fields or previously_configured
        else:
            variable.is_sensitive = False
            variable.provider_key = None
            variable.value = plain[field_name]
            variable.is_configured = plain[field_name] is not None
        synced.append(variable)
    for stale in existing.values():
        session.delete(stale)
    profile.variables = synced
    # New writes use the normalized variable table as the sole source for
    # ordinary connector settings. Keep the JSON column empty going forward.
    profile.config_json = {}


def _sync_profile_secret_document(
    session: Session,
    profile: ConnectorConfigurationModel,
    *,
    values: dict[str, str],
    user_id: int,
    old_provider_key: str | None,
    old_refs: dict[str, str],
) -> None:
    provider_key = (profile.provider_key or str(uuid4())) if values else None
    profile.provider_key = provider_key
    if values:
        assert provider_key is not None
        if old_provider_key != provider_key:
            _schedule_connector_secret_cleanup(
                session,
                tenant_id=profile.m8f_tenant_id,
                kind="document",
                key=provider_key,
                staged=True,
            )
        set_connector_configuration(
            session,
            tenant_id=profile.m8f_tenant_id,
            configuration_id=provider_key,
            values=values,
            user_id=user_id,
            replace_existing=False,
        )
        if get_connector_configuration(
            session,
            tenant_id=profile.m8f_tenant_id,
            configuration_id=provider_key,
        ) != values:
            raise ApiError(
                "connector_profile_error",
                "The connector credentials could not be verified after storage.",
                503,
            )
    # Remove old per-field secrets and the numeric-key document only after the
    # replacement document is verified and the profile transaction commits.
    # This also migrates profiles created before the single-document UUID format.
    for key in set(old_refs.values()):
        if key != provider_key and key != old_provider_key:
            _schedule_connector_secret_cleanup(
                session,
                tenant_id=profile.m8f_tenant_id,
                kind="secret",
                key=key,
            )
    if old_provider_key and (old_provider_key != provider_key or not values):
        _schedule_connector_secret_cleanup(
            session,
            tenant_id=profile.m8f_tenant_id,
            kind="document",
            key=old_provider_key,
        )
    profile.schema_version = "1"


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


def _split_profile_values(
    connector_type: str,
    submitted: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    fields = {
        str(field["id"]): field
        for field in (template_for(connector_type) or {}).get("profileFields", [])
        if isinstance(field.get("id"), str) and field.get("id")
    }
    unknown = [name for name in submitted if name not in fields]
    if unknown:
        raise ApiError(
            "validation_error",
            f"Unknown profile fields: {', '.join(sorted(unknown))}.",
            400,
        )
    sensitive_names = secret_field_names(connector_type)
    plain_values: dict[str, Any] = {}
    sensitive_values: dict[str, str] = {}
    for name, raw in submitted.items():
        if raw is None or raw == "":
            continue
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise ApiError("validation_error", f"{name} must be a scalar value.", 400)
        if name in sensitive_names:
            sensitive_values[name] = str(raw)
        else:
            plain_values[name] = str(raw)
    return plain_values, sensitive_values


def _update_profile_values(
    session: Session,
    profile: ConnectorConfigurationModel,
    *,
    submitted: dict[str, Any],
    clear: list[str],
 ) -> tuple[dict[str, Any], dict[str, str]]:
    plain_values, sensitive_values = _current_profile_values(session, profile)
    submitted_plain, submitted_sensitive = _split_profile_values(
        profile.connector_type, submitted
    )
    fields = {
        str(field["id"]): field
        for field in (template_for(profile.connector_type) or {}).get("profileFields", [])
        if isinstance(field.get("id"), str) and field.get("id")
    }
    unknown = sorted({name for name in clear if name not in fields})
    if unknown:
        raise ApiError(
            "validation_error", f"Unknown profile fields: {', '.join(unknown)}.", 400
        )
    for name in clear:
        meta = fields[name]
        label = meta.get("label", name)
        if meta.get("required"):
            raise ApiError(
                "validation_error", f"{label} is required and cannot be cleared.", 400
            )
        if name in submitted_plain or name in submitted_sensitive:
            raise ApiError(
                "validation_error", f"{label} cannot be both set and cleared.", 400
            )
    plain_values.update(submitted_plain)
    sensitive_values.update(submitted_sensitive)
    for name in clear:
        plain_values.pop(name, None)
        sensitive_values.pop(name, None)
    return plain_values, sensitive_values


def _current_profile_values(
    session: Session,
    profile: ConnectorConfigurationModel,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Load current values, including the previous field-secret format."""
    plain_values: dict[str, Any] = dict(profile.config_json or {})
    sensitive_values: dict[str, str] = {}
    sensitive_names = secret_field_names(profile.connector_type)
    refs = _profile_secret_refs(session, profile)
    document = (
        get_connector_configuration(
            session,
            tenant_id=profile.m8f_tenant_id,
            configuration_id=profile.provider_key,
        )
        if profile.provider_key
        and any(key == profile.provider_key for key in refs.values())
        else None
    )
    for name, value in (document or {}).items():
        if name in sensitive_names:
            sensitive_values[name] = value
        else:
            plain_values[name] = value

    for name, key in refs.items():
        if name in sensitive_values or name in plain_values or key == profile.provider_key:
            continue
        try:
            value = get_secret_value(session, tenant_id=profile.m8f_tenant_id, key=key)
        except ApiError as exc:
            if exc.status_code == 404:
                continue
            raise
        if value is None:
            continue
        if name in sensitive_names:
            sensitive_values[name] = value
        else:
            plain_values[name] = value

    for row in _profile_variable_rows(session, profile):
        if row.field_name in sensitive_names:
            if (
                row.field_name not in sensitive_values
                and row.provider_key
                and row.provider_key != profile.provider_key
            ):
                try:
                    value = get_secret_value(
                        session,
                        tenant_id=profile.m8f_tenant_id,
                        key=row.provider_key,
                    )
                except ApiError as exc:
                    if exc.status_code != 404:
                        raise
                else:
                    if value is not None:
                        sensitive_values[row.field_name] = value
        elif row.value is not None:
            plain_values[row.field_name] = row.value

    # Older deployments stored every descriptor field in config_json or the
    # provider document. Reclassify these values with current metadata.
    for name in tuple(plain_values):
        if name in sensitive_names:
            sensitive_values[name] = str(plain_values.pop(name))
    return plain_values, sensitive_values


def _legacy_profile_value(
    session: Session,
    profile: ConnectorConfigurationModel,
    name: str,
) -> Any | None:
    key = _profile_secret_refs(session, profile).get(name)
    if key and key == profile.provider_key:
        document = get_connector_configuration(
            session,
            tenant_id=profile.m8f_tenant_id,
            configuration_id=profile.provider_key,
        )
        if document is not None and name in document:
            return document[name]
    return (
        get_secret_value(session, tenant_id=profile.m8f_tenant_id, key=key)
        if key and key != profile.provider_key
        else None
    )


def _is_uuid_key(value: str | None) -> bool:
    if not value:
        return False
    try:
        return str(UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False
