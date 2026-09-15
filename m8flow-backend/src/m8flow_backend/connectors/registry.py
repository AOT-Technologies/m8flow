"""The connector registry.

Definitions register at import time. Adding a connector is a code change with
no migration: ``connector_type`` is validated against this registry in the
application layer rather than by a SQL CHECK constraint.
"""

from __future__ import annotations

import re

from m8flow_backend.connectors.base import (
    CONFIG_PARAM,
    MAX_SECRET_FIELD_NAME_LENGTH,
    SECRET_PARAM,
    TASK_PARAM,
    ConnectorDefinition,
)

CONNECTOR_REGISTRY: dict[str, type[ConnectorDefinition]] = {}
_SCHEMA_VERSION_RE = re.compile(r"^[1-9][0-9]*$")


def register(cls: type[ConnectorDefinition]) -> type[ConnectorDefinition]:
    """Register a definition, rejecting anything that cannot work at runtime.

    Both checks below fail at import time rather than when a user first tries
    to save a profile, so a bad definition cannot reach a release.
    """
    connector_type = cls.connector_type

    if not _SCHEMA_VERSION_RE.fullmatch(cls.schema_version):
        raise ValueError(
            f"{cls.__name__}.schema_version must be a positive integer string."
        )

    if connector_type in CONNECTOR_REGISTRY and CONNECTOR_REGISTRY[connector_type] is not cls:
        raise ValueError(
            f"Connector type '{connector_type}' is already registered by "
            f"{CONNECTOR_REGISTRY[connector_type].__name__}."
        )

    for name in cls.secret_field_names():
        if len(name) > MAX_SECRET_FIELD_NAME_LENGTH:
            raise ValueError(
                f"{cls.__name__}.{name}: secret field names must be at most "
                f"{MAX_SECRET_FIELD_NAME_LENGTH} characters so the secret-store key "
                f"fits upstream's 50-character key column."
            )

    declared_groups = {group["id"] for group in cls.groups}
    for name, field in cls.model_fields.items():
        extra = field.json_schema_extra or {}
        group = extra.get("group")
        if group is not None and declared_groups and group not in declared_groups:
            raise ValueError(
                f"{cls.__name__}.{name}: group '{group}' is not declared in "
                f"{cls.__name__}.groups."
            )
        binding = extra.get("binding")
        if binding is not None and binding not in {CONFIG_PARAM, SECRET_PARAM, TASK_PARAM}:
            raise ValueError(
                f"{cls.__name__}.{name}: unsupported field binding '{binding}'."
            )

    CONNECTOR_REGISTRY[connector_type] = cls
    return cls


def get_connector(connector_type: str) -> type[ConnectorDefinition] | None:
    """The definition for a connector type, or None when unknown."""
    _ensure_loaded()
    return CONNECTOR_REGISTRY.get(connector_type)


def all_connectors() -> list[type[ConnectorDefinition]]:
    """Every registered definition, ordered by display name."""
    _ensure_loaded()
    return sorted(CONNECTOR_REGISTRY.values(), key=lambda cls: cls.display_name.lower())


def _ensure_loaded() -> None:
    """Import the definition modules so their @register calls have run."""
    from m8flow_backend.connectors import definitions  # noqa: F401
