"""Create, read and resolve connector profiles.

A profile is a named credential/configuration set for one connector in one
tenant. Non-sensitive values are stored on the configuration row; sensitive
ones go to the secret store and the row keeps only their keys.

Write ordering (create): insert the row first so the configuration id exists,
then write each secret under a key derived from that id, then record the keys
back on the row. A failure part-way deletes what was written and rolls the row
back, so a half-made profile never survives.
"""

from __future__ import annotations

import logging
from typing import Any

from spiffworkflow_backend.models.db import db

from m8flow_backend.connectors.base import ConnectorDefinition, secret_ref
from m8flow_backend.connectors.registry import get_connector
from m8flow_backend.models.connector_configuration import ConnectorConfigurationModel
from m8flow_backend.services.connector_secret_backend import secret_backend
from m8flow_backend.tenancy import get_tenant_id

logger = logging.getLogger(__name__)

# The service-task parameter a BPMN author sets (through the modeler dropdown)
# to bind a task to a profile.
PROFILE_PARAMETER_NAME = "m8flow_profile"


class ConnectorProfileError(Exception):
    """A profile could not be created, updated or resolved."""

    def __init__(self, message: str, *, status_code: int = 400, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.errors = errors or []


class ConnectorProfileService:
    @staticmethod
    def _tenant_query():
        """Configurations of the active tenant.

        The tenant filter is written out rather than left to the tenant scoping
        patch and RLS. Those still apply - this is the first of the three
        layers, and the one that is visible at the call site.
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
                f"Connector '{connector_type}' does not use profiles.", status_code=400
            )
        return definition

    # ------------------------------------------------------------------ read

    @classmethod
    def list_profiles(cls, connector_type: str | None = None) -> list[ConnectorConfigurationModel]:
        query = cls._tenant_query()
        if connector_type:
            query = query.filter(ConnectorConfigurationModel.connector_type == connector_type)
        return query.order_by(
            ConnectorConfigurationModel.connector_type,
            ConnectorConfigurationModel.profile_name,
        ).all()

    @classmethod
    def get_profile(cls, configuration_id: int) -> ConnectorConfigurationModel:
        profile = cls._tenant_query().filter(
            ConnectorConfigurationModel.id == configuration_id
        ).first()
        if profile is None:
            # Also the answer for another tenant's row: the query is tenant
            # scoped, so a cross-tenant id is indistinguishable from a missing one.
            raise ConnectorProfileError("Connector profile not found.", status_code=404)
        return profile

    @classmethod
    def profile_counts(cls) -> dict[str, int]:
        """Active profile count per connector type for the current tenant."""
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
    def create_profile(cls, body: dict[str, Any], user_id: int | None) -> ConnectorConfigurationModel:
        connector_type = (body.get("connector_type") or "").strip()
        definition = cls.definition_or_raise(connector_type)

        profile_name = cls._validated_profile_name(body.get("profile_name"))
        display_name = (body.get("display_name") or profile_name).strip()

        cleaned, errors = definition.validate_profile(body.get("config") or {})
        if errors:
            raise ConnectorProfileError(
                "Connector profile is not valid.",
                status_code=400,
                errors=[error.to_dict() for error in errors],
            )

        if cls._name_taken(connector_type, profile_name):
            raise ConnectorProfileError(
                f"A '{profile_name}' profile already exists for this connector.",
                status_code=409,
            )

        config_values, secret_values = cls._split(definition, cleaned)

        profile = ConnectorConfigurationModel(
            m8f_tenant_id=get_tenant_id(),
            connector_type=connector_type,
            profile_name=profile_name,
            display_name=display_name,
            description=(body.get("description") or None),
            config_json=config_values,
            secret_refs={},
            is_active=bool(body.get("is_active", True)),
            is_default=False,
            user_id=user_id,
        )
        db.session.add(profile)
        db.session.commit()

        written: dict[str, str] = {}
        try:
            for field_name, value in secret_values.items():
                key = secret_ref(profile.id, field_name)
                secret_backend().upsert(key, value, user_id)
                written[field_name] = key
            profile.secret_refs = written
            db.session.add(profile)
            db.session.commit()
        except Exception:
            cls._discard(profile, written)
            raise

        if body.get("is_default"):
            cls.set_default(profile.id)

        return profile

    @classmethod
    def update_profile(
        cls, configuration_id: int, body: dict[str, Any], user_id: int | None
    ) -> ConnectorConfigurationModel:
        profile = cls.get_profile(configuration_id)
        definition = cls.definition_or_raise(profile.connector_type)

        if "profile_name" in body:
            new_name = cls._validated_profile_name(body.get("profile_name"))
            if new_name != profile.profile_name and cls._name_taken(profile.connector_type, new_name):
                raise ConnectorProfileError(
                    f"A '{new_name}' profile already exists for this connector.", status_code=409
                )
            profile.profile_name = new_name

        if "display_name" in body and body["display_name"]:
            profile.display_name = str(body["display_name"]).strip()
        if "description" in body:
            profile.description = body["description"] or None
        if "is_active" in body:
            profile.is_active = bool(body["is_active"])

        submitted = body.get("config")
        if submitted is not None:
            submitted = cls._drop_untouched_secrets(definition, submitted)
            cleaned, errors = definition.validate_profile(submitted, partial=True)
            if errors:
                raise ConnectorProfileError(
                    "Connector profile is not valid.",
                    status_code=400,
                    errors=[error.to_dict() for error in errors],
                )
            config_values, secret_values = cls._split(definition, cleaned)

            merged_config = dict(profile.config_json or {})
            merged_config.update(config_values)
            profile.config_json = merged_config

            refs = dict(profile.secret_refs or {})
            for field_name, value in secret_values.items():
                key = secret_ref(profile.id, field_name)
                if value is None:
                    # An explicit blank clears the secret; a field simply left
                    # out of the request keeps its current value.
                    secret_backend().delete(key)
                    refs.pop(field_name, None)
                else:
                    secret_backend().upsert(key, value, user_id)
                    refs[field_name] = key
            profile.secret_refs = refs

        db.session.add(profile)
        db.session.commit()

        if body.get("is_default"):
            cls.set_default(profile.id)

        return profile

    @classmethod
    def delete_profile(cls, configuration_id: int) -> None:
        profile = cls.get_profile(configuration_id)
        refs = list((profile.secret_refs or {}).values())

        db.session.delete(profile)
        db.session.commit()

        for key in refs:
            try:
                secret_backend().delete(key)
            except Exception:
                # The row is already gone, so the profile is deleted as far as
                # the user is concerned. Log the leftover instead of failing.
                logger.warning("Could not delete connector profile secret '%s'", key, exc_info=True)

    @classmethod
    def set_default(cls, configuration_id: int) -> ConnectorConfigurationModel:
        """Make one profile the connector's default, demoting any other."""
        profile = cls.get_profile(configuration_id)
        others = (
            cls._tenant_query()
            .filter(ConnectorConfigurationModel.connector_type == profile.connector_type)
            .filter(ConnectorConfigurationModel.id != profile.id)
            .filter(ConnectorConfigurationModel.is_default.is_(True))
            .all()
        )
        for other in others:
            other.is_default = False
            db.session.add(other)
        profile.is_default = True
        db.session.add(profile)
        db.session.commit()
        return profile

    # --------------------------------------------------------------- runtime

    @classmethod
    def resolve_for_runtime(cls, connector_type: str, profile_name: str) -> dict[str, Any]:
        """Values a service task inherits from a profile.

        Raises when the profile is missing or inactive: a connector call must
        never silently proceed without the credentials it was told to use.
        """
        profile = (
            cls._tenant_query()
            .filter(ConnectorConfigurationModel.connector_type == connector_type)
            .filter(ConnectorConfigurationModel.profile_name == profile_name)
            .first()
        )
        if profile is None:
            raise ConnectorProfileError(
                f"No '{profile_name}' profile is configured for connector '{connector_type}'.",
                status_code=404,
            )
        if not profile.is_active:
            raise ConnectorProfileError(
                f"Connector profile '{profile_name}' is disabled.", status_code=409
            )

        resolved: dict[str, Any] = {
            name: value for name, value in (profile.config_json or {}).items() if value is not None
        }
        for field_name, key in (profile.secret_refs or {}).items():
            value = secret_backend().get(key)
            if value is None:
                raise ConnectorProfileError(
                    f"Connector profile '{profile_name}' is missing its stored"
                    f" value for '{field_name}'.",
                    status_code=409,
                )
            resolved[field_name] = value
        return resolved

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _split(
        definition: type[ConnectorDefinition], cleaned: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Separate validated values into config values and secret values."""
        secret_names = {f.name for f in definition.secret_fields()}
        config_values = {k: v for k, v in cleaned.items() if k not in secret_names}
        secret_values = {k: v for k, v in cleaned.items() if k in secret_names}
        return config_values, secret_values

    @staticmethod
    def _drop_untouched_secrets(
        definition: type[ConnectorDefinition], submitted: dict[str, Any]
    ) -> dict[str, Any]:
        """Blank secret means "keep what is stored"; JSON null means "clear it".

        Stored secrets are never sent back to the browser, so the edit form
        posts a blank box for any secret the user did not retype. Treating that
        as a clear would wipe credentials on an unrelated edit.
        """
        secret_names = {f.name for f in definition.secret_fields()}
        return {
            name: value
            for name, value in submitted.items()
            if not (name in secret_names and isinstance(value, str) and value.strip() == "")
        }

    @staticmethod
    def _validated_profile_name(raw: Any) -> str:
        name = (str(raw or "")).strip()
        if not name:
            raise ConnectorProfileError(
                "Profile name is required.",
                errors=[{"loc": ["profile_name"], "msg": "Profile name is required", "type": "missing"}],
            )
        if len(name) > 255:
            raise ConnectorProfileError(
                "Profile name is too long.",
                errors=[{"loc": ["profile_name"], "msg": "Profile name is too long", "type": "too_long"}],
            )
        return name

    @classmethod
    def _name_taken(cls, connector_type: str, profile_name: str) -> bool:
        return (
            cls._tenant_query()
            .filter(ConnectorConfigurationModel.connector_type == connector_type)
            .filter(ConnectorConfigurationModel.profile_name == profile_name)
            .first()
            is not None
        )

    @staticmethod
    def _discard(profile: ConnectorConfigurationModel, written: dict[str, str]) -> None:
        """Undo a partially created profile."""
        for key in written.values():
            try:
                secret_backend().delete(key)
            except Exception:
                logger.warning("Could not clean up connector profile secret '%s'", key, exc_info=True)
        try:
            db.session.delete(profile)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.warning("Could not roll back connector profile %s", profile.id, exc_info=True)
