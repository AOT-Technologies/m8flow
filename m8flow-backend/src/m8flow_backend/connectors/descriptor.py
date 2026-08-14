"""Serialize connector definitions to the JSON the frontend renders.

Two consumers:

* the Connectors screens, which build the profile form from ``profileFields``;
* the modeler, which uses ``profileFields`` to know which service-task
  parameters a selected profile supplies (and can therefore hide).

Secret *values* never appear here - a descriptor only describes shape.
"""

from __future__ import annotations

from typing import Any

from m8flow_backend.connectors.base import ConnectorDefinition, ConnectorField

_DOCS_BASE = "https://github.com/AOT-Technologies/m8flow/tree/main/m8flow-connector-proxy"


def field_descriptor(connector_field: ConnectorField) -> dict[str, Any]:
    """One form field, in the shape ConnectorConfigure renders."""
    descriptor: dict[str, Any] = {
        "id": connector_field.name,
        "label": connector_field.label,
        "type": connector_field.type,
        "required": connector_field.required,
        "group": connector_field.group,
        "binding": connector_field.binding,
        "secret": connector_field.is_secret,
    }
    if connector_field.default is not None:
        descriptor["default"] = connector_field.default
    if connector_field.choices:
        descriptor["choices"] = [
            {"value": choice.value, "label": choice.label} for choice in connector_field.choices
        ]
    if connector_field.format:
        descriptor["format"] = connector_field.format
    if connector_field.min_length is not None:
        descriptor["minLength"] = connector_field.min_length
    if connector_field.max_length is not None:
        descriptor["maxLength"] = connector_field.max_length
    if connector_field.help_text:
        descriptor["helpText"] = connector_field.help_text
    if connector_field.example:
        descriptor["example"] = connector_field.example
    return descriptor


def docs_url(cls: type[ConnectorDefinition]) -> str:
    return f"{_DOCS_BASE}{cls.docs_anchor}" if cls.docs_anchor else _DOCS_BASE


def to_descriptor(cls: type[ConnectorDefinition]) -> dict[str, Any]:
    """Full descriptor for one connector."""
    return {
        "id": cls.connector_type,
        "name": cls.display_name,
        "description": cls.description,
        "category": cls.category,
        "icon": cls.icon,
        "docsUrl": docs_url(cls),
        "supportsProfiles": cls.has_profile_support(),
        "testOperation": cls.test_operation,
        "groups": [{"id": group.id, "label": group.label} for group in cls.groups],
        "profileFields": [field_descriptor(f) for f in cls.profile_fields()],
        "taskFields": [field_descriptor(f) for f in cls.task_fields()],
    }


def all_descriptors() -> list[dict[str, Any]]:
    from m8flow_backend.connectors.registry import all_connectors

    return [to_descriptor(cls) for cls in all_connectors()]
