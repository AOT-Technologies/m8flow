"""Registry of connector definitions.

Definitions are code, so adding a connector is a code change only: write the
module, decorate the class with ``@register``, import it from
``definitions/__init__.py``. No migration, no template upload, no file sync.
"""

from __future__ import annotations

from m8flow_backend.connectors.base import (
    MAX_SECRET_FIELD_NAME_LENGTH,
    ConnectorDefinition,
)

CONNECTOR_REGISTRY: dict[str, type[ConnectorDefinition]] = {}


def register(cls: type[ConnectorDefinition]) -> type[ConnectorDefinition]:
    """Class decorator adding a definition to the registry."""
    connector_type = cls.connector_type
    if not connector_type:
        raise ValueError(f"{cls.__name__} must set connector_type")

    existing = CONNECTOR_REGISTRY.get(connector_type)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"connector_type '{connector_type}' is already registered by {existing.__name__}"
        )

    duplicate_names = _duplicate_field_names(cls)
    if duplicate_names:
        raise ValueError(
            f"{cls.__name__} declares duplicate field names: {', '.join(sorted(duplicate_names))}"
        )

    for connector_field in cls.secret_fields():
        if len(connector_field.name) > MAX_SECRET_FIELD_NAME_LENGTH:
            raise ValueError(
                f"{cls.__name__} secret field '{connector_field.name}' is too long: its"
                f" secret-store key would not fit (max {MAX_SECRET_FIELD_NAME_LENGTH} chars)"
            )

    CONNECTOR_REGISTRY[connector_type] = cls
    return cls


def _duplicate_field_names(cls: type[ConnectorDefinition]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for connector_field in cls.fields:
        if connector_field.name in seen:
            duplicates.add(connector_field.name)
        seen.add(connector_field.name)
    return duplicates


def get_connector(connector_type: str) -> type[ConnectorDefinition] | None:
    """Definition for a connector type, or None when it has no definition yet.

    Returning None rather than raising is deliberate: the proxy can serve
    connectors this backend knows nothing about, and those must keep working
    with manually entered parameters.
    """
    _load_definitions()
    return CONNECTOR_REGISTRY.get(connector_type)


def all_connectors() -> list[type[ConnectorDefinition]]:
    """Every registered definition, ordered by display name."""
    _load_definitions()
    return sorted(CONNECTOR_REGISTRY.values(), key=lambda cls: cls.display_name.lower())


_DEFINITIONS_LOADED = False


def _load_definitions() -> None:
    """Import the definition modules once, on first lookup."""
    global _DEFINITIONS_LOADED
    if _DEFINITIONS_LOADED:
        return
    # Imported for the @register side effect.
    from m8flow_backend.connectors import definitions  # noqa: F401

    _DEFINITIONS_LOADED = True
