"""Serialize a definition to the JSON the frontend renders.

Field ``type``/``format``/``minLength``/``maxLength`` are emitted in the exact
vocabulary ``m8flow-frontend/src/utils/connectorFieldValidation.ts`` already
validates against, so the profile form reuses that validator rather than
introducing a second contract.
"""

from __future__ import annotations

from typing import Any

from m8flow_backend.connectors.base import (
    PROFILE_BINDINGS,
    SECRET_PARAM,
    TASK_PARAM,
    ConnectorDefinition,
    unwrap_annotation,
)

_DOCS_BASE = "https://github.com/AOT-Technologies/m8flow/tree/main/m8flow-connector-proxy"

# Python type -> the widget vocabulary the frontend validator understands.
_WIDGET_BY_TYPE: dict[Any, str] = {
    str: "text",
    int: "number",
    float: "number",
    bool: "boolean",
}


def _widget(annotation: Any, extra: dict[str, Any], choices: tuple[Any, ...]) -> str:
    explicit = extra.get("widget")
    if explicit:
        return explicit
    if choices:
        return "select"
    return _WIDGET_BY_TYPE.get(annotation, "text")


def field_descriptor(name: str, field: Any) -> dict[str, Any]:
    """One field, in the frontend's form-field shape."""
    extra = dict(field.json_schema_extra or {})
    annotation, optional, choices = unwrap_annotation(field.annotation)

    # `required` is a property of the declaration, not of pydantic's default:
    # every field carries default=None so a phase-1 payload can omit runtime
    # fields, so requiredness is declared explicitly instead.
    required = bool(extra.get("required", not optional))

    descriptor: dict[str, Any] = {
        # The wire name, not the python attribute: the frontend uses this id to
        # match bpmn parameter rows, which carry the proxy's names.
        "id": extra.get("wire_name") or name,
        "label": extra.get("label", name.replace("_", " ").title()),
        "type": _widget(annotation, extra, choices),
        "required": required,
        "group": extra.get("group", "connection"),
        "binding": extra.get("binding"),
        "secret": extra.get("binding") == SECRET_PARAM,
    }

    if choices:
        declared = extra.get("choices")
        if declared:
            descriptor["choices"] = list(declared)
        else:
            descriptor["choices"] = [{"value": value, "label": str(value)} for value in choices]

    for source, target in (
        ("format", "format"),
        ("min_length", "minLength"),
        ("max_length", "maxLength"),
        ("help_text", "helpText"),
        ("example", "example"),
        ("description", "description"),
        ("is_highly_sensitive", "isHighlySensitive"),
        ("python_expression", "pythonExpression"),
    ):
        if source in extra:
            descriptor[target] = extra[source]

    default = extra.get("default_value")
    if default is not None:
        descriptor["default"] = default

    return descriptor


def to_descriptor(cls: type[ConnectorDefinition]) -> dict[str, Any]:
    """The full descriptor for one connector.

    ``profileFields`` are what a saved profile supplies (and what the modeler
    hides once a profile is picked); ``taskFields`` stay on the service task.
    """
    profile_fields: list[dict[str, Any]] = []
    task_fields: list[dict[str, Any]] = []

    for name, field in cls.model_fields.items():
        binding = (field.json_schema_extra or {}).get("binding")
        descriptor = field_descriptor(name, field)
        if binding in PROFILE_BINDINGS:
            profile_fields.append(descriptor)
        elif binding == TASK_PARAM:
            task_fields.append(descriptor)

    return {
        "id": cls.connector_type,
        "definitionId": cls.id,
        "name": cls.display_name,
        "description": cls.description,
        "category": cls.category,
        "icon": cls.icon,
        "docsUrl": f"{_DOCS_BASE}#{cls.docs_anchor}" if cls.docs_anchor else _DOCS_BASE,
        "supportsProfiles": cls.has_profile_support(),
        "groups": [dict(group) for group in cls.groups],
        "profileFields": profile_fields,
        "taskFields": task_fields,
    }
