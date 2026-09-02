"""Field metadata and the base class every connector definition subclasses.

A connector definition is the one place that says what a connector needs, and
which lifecycle each value belongs to. Three bindings (M8Flow.md 4.1):

``config_param``
    Non-sensitive profile value -> ``connector_configuration.config_json``.
``secret_param``
    Sensitive profile value -> the secret store; the row keeps only a reference
    in ``connector_configuration.secret_refs``.
``task_param``
    Never persisted. The BPMN service task supplies it per run.

Field names are a hard contract, not a label. Each must be the exact keyword
argument of the matching command in the connector proxy, because the proxy
builds commands as ``command(**params)`` and dies on an unknown name. The names
here were taken from the shipped connectors (m8flow-connector-proxy/README.md)
and cross-checked against the sample templates' BPMN, not from the design note,
whose illustrative names differ.
"""

from __future__ import annotations

import base64
import types
import uuid
from typing import Annotated, Any, ClassVar, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

CONFIG_PARAM = "config_param"
SECRET_PARAM = "secret_param"
TASK_PARAM = "task_param"

PROFILE_BINDINGS = (CONFIG_PARAM, SECRET_PARAM)

# Secret-store key layout for profile secrets: cnx.<configuration id>.<field>.
# Keyed on the immutable configuration id rather than the profile name, so
# renaming a profile touches nothing in the secret store.
#
# The separator must not be "/": the secret API addresses a key as a single
# path segment (/secrets/{key}), and WSGI decodes %2F back into PATH_INFO
# before routing, so a slashed key is unreachable however it is encoded.
SECRET_REF_PREFIX = "cnx"
SECRET_REF_SEPARATOR = "."
# Upstream's secret.key column is VARCHAR(50) and widening an upstream table is
# out of bounds, so keys must fit that budget. The registry rejects any field
# name that cannot.
SECRET_KEY_MAX_LENGTH = 50
# Legacy per-field refs must fit upstream's 50-character key limit, including
# the field name. URL-safe base64 encodes a UUID in 22 characters without
# padding, while remaining reversible and collision-free.
_CONFIG_ID_DIGITS = 22
MAX_SECRET_FIELD_NAME_LENGTH = (
    SECRET_KEY_MAX_LENGTH - len(SECRET_REF_PREFIX) - 2 - _CONFIG_ID_DIGITS
)


def secret_ref(configuration_id: str, field_name: str) -> str:
    """The secret-store key holding one profile field's value."""
    encoded_id = base64.urlsafe_b64encode(uuid.UUID(configuration_id).bytes).decode(
        "ascii"
    ).rstrip("=")
    return f"{SECRET_REF_PREFIX}{SECRET_REF_SEPARATOR}{encoded_id}{SECRET_REF_SEPARATOR}{field_name}"


def config_param(group: str, **ui: Any) -> Any:
    """Non-sensitive profile value -> config_json."""
    return Field(default=None, json_schema_extra={"binding": CONFIG_PARAM, "group": group, **ui})


def secret_param(group: str, **ui: Any) -> Any:
    """Sensitive profile value -> secret provider; only state is persisted."""
    return Field(
        default=None,
        json_schema_extra={
            "binding": SECRET_PARAM,
            "group": group,
            # Sensitivity is binary. Widget choice is presentation only: a
            # username may render as text but is still never a database value.
            "widget": ui.pop("widget", "password"),
            **ui,
        },
    )


def task_param(**ui: Any) -> Any:
    """Run-time value -> supplied by the BPMN service task; never persisted."""
    return Field(default=None, json_schema_extra={"binding": TASK_PARAM, "python_expression": True, **ui})


class ConnectorDefinition(BaseModel):
    """Base class for every connector.

    Subclass fields declare the schema; the executor lives in the connector
    proxy, addressed by ``connector_type/OperationName``.
    """

    # Fields are optional at the class level because which ones are required
    # depends on the lifecycle phase: a profile save validates the connection
    # subset, a run validates the whole thing. `validation.py` builds the
    # phase-specific model that enforces requiredness.
    model_config = ConfigDict(extra="forbid")

    id: ClassVar[str]
    connector_type: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str] = ""
    category: ClassVar[str] = "integration"
    icon: ClassVar[str] = "extension"
    groups: ClassVar[tuple[dict[str, str], ...]] = ()
    docs_anchor: ClassVar[str | None] = None
    # Persisted profiles record this value once the field-level schema cutover
    # is active. Bump it when a connector's profile field contract changes.
    schema_version: ClassVar[str] = "1"

    @classmethod
    def wire_name(cls, name: str) -> str:
        """The parameter name the connector proxy expects for this field.

        Almost always the field name itself. The indirection exists for the rare
        field whose real name collides with a pydantic attribute (postgres's
        ``schema``), which must still reach the proxy under its own name.
        """
        field = cls.model_fields.get(name)
        if field is None:
            return name
        return (field.json_schema_extra or {}).get("wire_name") or name

    @classmethod
    def wire_names(cls, *bindings: str) -> tuple[str, ...]:
        """Wire names for the fields in the given bindings."""
        return tuple(
            cls.wire_name(name) for name in cls.field_names_for_binding(*bindings)
        )

    @classmethod
    def field_binding(cls, name: str) -> str | None:
        field = cls.model_fields.get(name)
        if field is None:
            return None
        return (field.json_schema_extra or {}).get("binding")

    @classmethod
    def field_names_for_binding(cls, *bindings: str) -> tuple[str, ...]:
        return tuple(
            name
            for name, field in cls.model_fields.items()
            if (field.json_schema_extra or {}).get("binding") in bindings
        )

    @classmethod
    def profile_field_names(cls) -> tuple[str, ...]:
        """Fields a saved profile supplies. These are hidden in the modeler."""
        return cls.field_names_for_binding(*PROFILE_BINDINGS)

    @classmethod
    def secret_field_names(cls) -> tuple[str, ...]:
        return cls.field_names_for_binding(SECRET_PARAM)

    @classmethod
    def field_is_sensitive(cls, name: str) -> bool:
        """Whether the registry classifies a profile field as sensitive."""
        return cls.field_binding(name) == SECRET_PARAM

    @classmethod
    def has_profile_support(cls) -> bool:
        """False for a connector with nothing worth saving in a profile."""
        return bool(cls.profile_field_names())


def unwrap_annotation(annotation: Any) -> tuple[Any, bool, tuple[Any, ...]]:
    """Reduce a field annotation to (base type, is_optional, literal choices).

    Handles the three wrappers the definitions use, in any nesting order:
    ``Annotated[...]``, ``X | None``, and ``Literal[...]``. Without this a
    ``Literal[25, 587, 465]`` would export as an opaque type and a ``str | None``
    would export as required.
    """
    optional = False
    choices: tuple[Any, ...] = ()

    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
            continue
        if origin is Union or origin is types.UnionType:
            args = [a for a in get_args(annotation) if a is not type(None)]
            optional = optional or len(args) != len(get_args(annotation))
            if len(args) == 1:
                annotation = args[0]
                continue
            return (str, optional, choices)
        if origin is Literal:
            literal_values = get_args(annotation)
            # A Literal may include None to express optionality.
            choices = tuple(v for v in literal_values if v is not None)
            optional = optional or len(choices) != len(literal_values)
            annotation = type(choices[0]) if choices else str
            continue
        return (annotation, optional, choices)
