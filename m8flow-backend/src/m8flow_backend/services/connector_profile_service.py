"""Create, read, update, delete and resolve connector profiles.

A profile is a named credential/configuration set for one connector in one
tenant. Non-sensitive values live on the configuration row; sensitive ones go
to the secret store and the row keeps only their keys.

Write ordering (M8Flow.md 6.4): insert the row first so the configuration id
exists, then write each secret under a key derived from that id, then record
the keys back on the row. The invariant that matters is that a committed row
never references a secret that was not created first; a failure part-way
deletes what was written and rolls the row back, so a half-made profile never
survives.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from spiffworkflow_backend.models.db import db

from m8flow_backend.connectors.base import (
    SECRET_PARAM,
    ConnectorDefinition,
    secret_ref,
)
from m8flow_backend.connectors.registry import get_connector
from m8flow_backend.connectors.validation import validate_profile
from m8flow_backend.models.connector_configuration import ConnectorConfigurationModel
from m8flow_backend.services.connector_secret_backend import secret_backend
from m8flow_backend.tenancy import get_tenant_id

logger = logging.getLogger(__name__)

# The service-task parameter a BPMN author sets, via the modeler dropdown, to
# bind a task to a profile.
PROFILE_PARAMETER_NAME = "m8flow_profile"

# Profile names travel through BPMN XML and secret-store keys, so they are kept
# to a conservative character set.
_PROFILE_NAME_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}[a-zA-Z0-9]$|^[a-zA-Z0-9]$"
)


class ConnectorProfileError(Exception):
    """A profile could not be created, read, updated or resolved."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        errors: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.errors = errors or []


class ConnectorProfileService:
    # ------------------------------------------------------------------ read

    @staticmethod
    def _tenant_query():
        """Configurations of the active tenant.

        The tenant filter is spelled out rather than left to the scoping patch
        and RLS. Those still apply -- this is the first of the three layers,
        and the one visible at the call site.
        """
        return ConnectorConfigurationModel.query.filter(
            ConnectorConfigurationModel.m8f_tenant_id == get_tenant_id()
        )

    @staticmethod
    def definition_or_raise(connector_type: str) -> type[ConnectorDefinition]:
        definition = get_connector(connector_type)
        if definition is None:
            raise ConnectorProfileError(
                f"Unknown connector type '{connector_type}'.", status_code=404
            )
        if not definition.has_profile_support():
            raise ConnectorProfileError(
                f"Connector '{connector_type}' has nothing to configure.",
                status_code=400,
            )
        return definition

    @classmethod
    def list_profiles(
        cls, connector_type: str | None = None, *, include_inactive: bool = True
    ) -> list[ConnectorConfigurationModel]:
        query = cls._tenant_query()
        if connector_type:
            query = query.filter(
                ConnectorConfigurationModel.connector_type == connector_type
            )
        if not include_inactive:
            query = query.filter(ConnectorConfigurationModel.is_active.is_(True))
        return query.order_by(
            ConnectorConfigurationModel.connector_type,
            ConnectorConfigurationModel.profile_name,
        ).all()

    @classmethod
    def get_profile(cls, configuration_id: int) -> ConnectorConfigurationModel:
        profile = (
            cls._tenant_query()
            .filter(ConnectorConfigurationModel.id == configuration_id)
            .first()
        )
        if profile is None:
            # Also the answer for another tenant's row: the query is tenant
            # scoped, so a cross-tenant id is indistinguishable from a missing
            # one, and 404 leaks nothing about what other tenants own.
            raise ConnectorProfileError("Connector profile not found.", status_code=404)
        return profile

    @classmethod
    def profile_counts(cls) -> dict[str, int]:
        """Active profile count per connector type, for the current tenant."""
        rows = (
            db.session.query(
                ConnectorConfigurationModel.connector_type,
                db.func.count(ConnectorConfigurationModel.id),
            )
            .filter(ConnectorConfigurationModel.m8f_tenant_id == get_tenant_id())
            .filter(ConnectorConfigurationModel.is_active.is_(True))
            .group_by(ConnectorConfigurationModel.connector_type)
            .all()
        )
        return {connector_type: count for connector_type, count in rows}

    # ----------------------------------------------------------------- write

    @classmethod
    def create_profile(
        cls, body: dict[str, Any], user_id: int | None
    ) -> ConnectorConfigurationModel:
        connector_type = (body.get("connector_type") or "").strip()
        definition = cls.definition_or_raise(connector_type)

        profile_name = cls._validated_profile_name(body.get("profile_name"))
        display_name = (body.get("display_name") or profile_name).strip()

        cleaned, errors = validate_profile(definition, body.get("config") or {})
        if errors:
            raise ConnectorProfileError(
                "Connector profile is not valid.", status_code=400, errors=errors
            )

        existing = cls._by_name(connector_type, profile_name)
        if existing is not None:
            raise cls._name_conflict(profile_name, existing)

        config_values, secret_values = cls._split(definition, cleaned)

        profile = ConnectorConfigurationModel(
            m8f_tenant_id=get_tenant_id(),
            connector_type=connector_type,
            profile_name=profile_name,
            display_name=display_name,
            description=(body.get("description") or None),
            config_json=config_values,
            secret_refs={},
            is_active=True,
            user_id=user_id,
        )
        db.session.add(profile)
        # Flush, not commit: the id must exist to build secret keys, but the row
        # must still be rollback-able if a secret write fails.
        db.session.flush()

        # Capture the generated id before the secret refs are attached, and log
        # it as a plain int, so nothing derived from the credentials reaches the
        # log line.
        new_profile_id = int(profile.id)
        profile.secret_refs = cls._write_secrets(new_profile_id, secret_values, user_id)

        db.session.commit()
        logger.info(
            "Created connector profile '%s' for connector '%s' (id=%s)",
            profile_name,
            connector_type,
            new_profile_id,
        )
        return profile

    @classmethod
    def update_profile(
        cls, configuration_id: int, body: dict[str, Any], user_id: int | None
    ) -> ConnectorConfigurationModel:
        profile = cls.get_profile(configuration_id)
        definition = cls.definition_or_raise(profile.connector_type)

        if body.get("display_name"):
            profile.display_name = str(body["display_name"]).strip()
        if "description" in body:
            profile.description = body["description"] or None
        if "is_active" in body:
            profile.is_active = bool(body["is_active"])

        if "config" in body:
            cls._update_config(profile, definition, dict(body["config"] or {}), user_id)

        db.session.commit()
        return profile

    @classmethod
    def _update_config(
        cls,
        profile: ConnectorConfigurationModel,
        definition: type[ConnectorDefinition],
        submitted: dict[str, Any],
        user_id: int | None,
    ) -> None:
        """Merge a config patch, treating blank secrets as "leave unchanged".

        Secret values are write-only, so the form cannot echo the current one
        back; an empty input therefore has to mean "keep it" rather than "wipe
        it", or every edit would destroy credentials the user never touched.
        """
        merged = dict(profile.config_json or {})
        for name, value in submitted.items():
            if definition.field_binding(name) == SECRET_PARAM:
                continue
            merged[name] = value

        secret_updates = {
            name: value
            for name, value in submitted.items()
            if definition.field_binding(name) == SECRET_PARAM
            and value not in (None, "")
        }

        # Validate against the merged config plus both new and already-stored
        # secrets, so an untouched required secret does not read as missing.
        for_validation = dict(merged)
        for_validation.update(secret_updates)
        for name in profile.secret_refs or {}:
            for_validation.setdefault(name, "unchanged")

        cleaned, errors = validate_profile(definition, for_validation)
        if errors:
            raise ConnectorProfileError(
                "Connector profile is not valid.", status_code=400, errors=errors
            )

        config_values, _ = cls._split(definition, cleaned)
        profile.config_json = config_values

        if not secret_updates:
            return

        refs = dict(profile.secret_refs or {})
        backend = secret_backend()
        for name, value in secret_updates.items():
            # Upsert against the existing reference: the ref is keyed on the
            # immutable configuration id, so it is stable and there is no
            # consistency window on update.
            key = refs.get(name) or secret_ref(profile.id, name)
            backend.upsert(key, str(value), user_id)
            refs[name] = key
        profile.secret_refs = refs

    @classmethod
    def deactivate_profile(cls, configuration_id: int) -> ConnectorConfigurationModel:
        """Soft delete.

        The profile leaves the modeler dropdown at once, and a run still naming
        it fails loudly rather than silently sending no credentials. The row and
        its secrets survive, so it can be reactivated.
        """
        profile = cls.get_profile(configuration_id)
        profile.is_active = False
        db.session.commit()
        return profile

    @classmethod
    def delete_profile(cls, configuration_id: int) -> None:
        """Hard delete: the row, then best-effort secret removal.

        Ordering per M8Flow.md 6.4 -- the row goes first, so a failure leaves
        unreachable secrets rather than a row pointing at secrets that are gone.
        """
        profile = cls.get_profile(configuration_id)
        refs = list((profile.secret_refs or {}).values())

        db.session.delete(profile)
        db.session.commit()

        backend = secret_backend()
        failed = 0
        for key in refs:
            try:
                backend.delete(key)
            except Exception:
                failed += 1
                # codeql[py/clear-text-logging-sensitive-data]: logs
                # configuration_id (an int). The loop variable `key` is a
                # secret-store reference name, not a credential, and is not
                # part of the message.
                logger.warning(
                    "Could not delete secret for removed profile %s",
                    configuration_id,
                    exc_info=True,
                )
        if failed:
            # A count, so ops can size the orphan cleanup without correlating
            # the per-key warnings above. Still no key names: see the CodeQL
            # note above, which this message is bound by too.
            logger.warning(
                "Removed profile %s left %s of %s secret(s) undeleted; "
                "they are unreachable but still stored.",
                configuration_id,
                failed,
                len(refs),
            )
        db.session.commit()

    # --------------------------------------------------------------- runtime

    @classmethod
    def resolve_for_runtime(
        cls, connector_type: str, profile_name: str
    ) -> dict[str, Any]:
        """Config values plus decrypted secrets for one profile.

        Decrypted values exist in memory only, for the duration of the call.
        """
        profile = (
            cls._tenant_query()
            .filter(ConnectorConfigurationModel.connector_type == connector_type)
            .filter(ConnectorConfigurationModel.profile_name == profile_name)
            .first()
        )
        if profile is None:
            raise ConnectorProfileError(
                f"No '{profile_name}' profile is configured for connector "
                f"'{connector_type}'.",
                status_code=404,
            )
        if not profile.is_active:
            raise ConnectorProfileError(
                f"Connector profile '{profile_name}' is inactive. Reactivate it "
                f"under Connectors, or pick another profile on this task.",
                status_code=400,
            )

        definition = get_connector(connector_type)

        def wire(name: str) -> str:
            # Stored under the python field name; sent under the proxy's name.
            return definition.wire_name(name) if definition is not None else name

        resolved: dict[str, Any] = {
            wire(name): value for name, value in (profile.config_json or {}).items()
        }
        backend = secret_backend()
        for name, key in (profile.secret_refs or {}).items():
            value = backend.get(key)
            if value is None:
                # A missing secret is a real misconfiguration: failing loudly
                # beats sending a partial credential set to a live system.
                raise ConnectorProfileError(
                    f"Profile '{profile_name}' is missing its stored value for "
                    f"'{name}'. Re-enter it under Connectors.",
                    status_code=500,
                )
            resolved[wire(name)] = value
        return resolved

    # ---------------------------------------------------------------- helper

    @staticmethod
    def _validated_profile_name(raw: Any) -> str:
        name = (raw or "").strip()
        if not _PROFILE_NAME_RE.match(name):
            raise ConnectorProfileError(
                "Profile name must be 1-64 characters of letters, digits, '.', "
                "'-' or '_', starting and ending with a letter or digit.",
                status_code=400,
                errors=[
                    {
                        "loc": ["profile_name"],
                        "msg": "Invalid profile name.",
                        "type": "value_error",
                    }
                ],
            )
        return name

    @classmethod
    def _by_name(
        cls, connector_type: str, profile_name: str
    ) -> ConnectorConfigurationModel | None:
        return (
            cls._tenant_query()
            .filter(ConnectorConfigurationModel.connector_type == connector_type)
            .filter(ConnectorConfigurationModel.profile_name == profile_name)
            .first()
        )

    @staticmethod
    def _name_conflict(
        profile_name: str, existing: ConnectorConfigurationModel
    ) -> ConnectorProfileError:
        """409 for a taken name, saying so plainly when the holder is inactive.

        A soft-deleted profile still occupies its name in the unique index, so
        without this the user would see a raw constraint error.
        """
        if existing.is_active:
            message = f"A '{profile_name}' profile already exists for this connector."
        else:
            message = (
                f"An inactive '{profile_name}' profile already exists for this "
                f"connector. Reactivate it, or delete it permanently, to reuse "
                f"the name."
            )
        return ConnectorProfileError(message, status_code=409)

    @staticmethod
    def _split(
        definition: type[ConnectorDefinition], cleaned: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Partition validated values into config (row) and secrets (store)."""
        config_values: dict[str, Any] = {}
        secret_values: dict[str, Any] = {}
        for name, value in cleaned.items():
            if definition.field_binding(name) == SECRET_PARAM:
                secret_values[name] = value
            else:
                config_values[name] = value
        return (config_values, secret_values)

    @staticmethod
    def _write_secrets(
        configuration_id: int, secret_values: dict[str, Any], user_id: int | None
    ) -> dict[str, str]:
        """Write each secret, compensating for whatever landed if one fails."""
        backend = secret_backend()
        refs: dict[str, str] = {}
        try:
            for name, value in secret_values.items():
                key = secret_ref(configuration_id, name)
                backend.create(key, str(value), user_id)
                refs[name] = key
        except Exception as exc:
            for key in refs.values():
                try:
                    backend.delete(key)
                except Exception:
                    logger.warning("Compensating delete failed", exc_info=True)
            db.session.rollback()
            raise ConnectorProfileError(
                "Could not store the profile's credentials.", status_code=500
            ) from exc
        return refs

