"""Field metadata and the base class every connector definition subclasses.

A connector definition is the single place that says what a connector needs:
which values belong to a saved *profile* (a named, per-tenant credential/config
set) and which values the BPMN author supplies on each service task.

Three bindings, matching the connector architecture note (M8flow.md 4.1):

``config_param``
    Non-sensitive profile value. Stored in ``connector_configuration.config_json``.
``secret_param``
    Sensitive profile value. Stored in the secret store; the configuration row
    keeps only a reference (``connector_configuration.secret_refs``).
``task_param``
    Never stored. The BPMN service task supplies it at run time.

Field ``name`` is not cosmetic: it must be the exact keyword argument of the
connector command in the connector proxy (``smtp_host``, ``token``,
``access_token``...). Profile values are injected into the proxy call under
these names, and the proxy instantiates commands with ``command(**params)``.

The layer is deliberately built on dataclasses rather than pydantic: the
validation needed here is shallow (type, required, choices, bounds) and the
backend image does not ship pydantic as a runtime dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

CONFIG_PARAM = "config_param"
SECRET_PARAM = "secret_param"
TASK_PARAM = "task_param"

# Secret-store key layout for profile secrets: cnx/<configuration id>/<field>.
# The configuration id (not the profile name) is what the key embeds, so
# renaming a profile touches nothing in the secret store.
SECRET_REF_PREFIX = "cnx"
# Upstream's secret.key column is VARCHAR(50). Rather than widen an upstream
# table, keys are kept inside that budget and the registry rejects any field
# name that could not fit.
SECRET_KEY_MAX_LENGTH = 50
_SECRET_REF_ID_BUDGET = 10  # room for a 10-digit configuration id
MAX_SECRET_FIELD_NAME_LENGTH = (
    SECRET_KEY_MAX_LENGTH - len(SECRET_REF_PREFIX) - 2 - _SECRET_REF_ID_BUDGET
)


def secret_ref(configuration_id: int, field_name: str) -> str:
    """The secret-store key holding one profile field's value."""
    return f"{SECRET_REF_PREFIX}/{configuration_id}/{field_name}"

# Field types, in the vocabulary the frontend form renderer already understands
# (see m8flow-frontend/src/utils/connectorFieldValidation.ts).
TEXT = "text"
PASSWORD = "password"  # noqa: S105 - a widget name, not a credential
NUMBER = "number"
BOOLEAN = "boolean"
SELECT = "select"


@dataclass(frozen=True)
class FieldGroup:
    """A titled section in the profile form."""

    id: str
    label: str


@dataclass(frozen=True)
class Choice:
    """One option of a ``SELECT`` field."""

    value: Any
    label: str


@dataclass(frozen=True)
class ConnectorField:
    """One declared input of a connector."""

    name: str
    label: str
    binding: str
    type: str = TEXT
    group: str = "connection"
    required: bool = False
    default: Any = None
    choices: tuple[Choice, ...] = ()
    # Input-format hint the frontend validates against: url | email | port | number.
    format: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    help_text: str | None = None
    example: str | None = None
    # True for values that must never be echoed back, not even masked-partially.
    is_highly_sensitive: bool = False

    @property
    def is_profile_field(self) -> bool:
        return self.binding in (CONFIG_PARAM, SECRET_PARAM)

    @property
    def is_secret(self) -> bool:
        return self.binding == SECRET_PARAM


def config_param(
    name: str,
    label: str,
    *,
    group: str = "connection",
    type: str = TEXT,
    required: bool = True,
    default: Any = None,
    choices: tuple[Choice, ...] = (),
    format: str | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    help_text: str | None = None,
    example: str | None = None,
) -> ConnectorField:
    """Non-sensitive profile value -> ``connector_configuration.config_json``."""
    return ConnectorField(
        name=name,
        label=label,
        binding=CONFIG_PARAM,
        type=type,
        group=group,
        required=required,
        default=default,
        choices=choices,
        format=format,
        min_length=min_length,
        max_length=max_length,
        help_text=help_text,
        example=example,
    )


def secret_param(
    name: str,
    label: str,
    *,
    group: str = "authentication",
    required: bool = True,
    is_highly_sensitive: bool = True,
    help_text: str | None = None,
    example: str | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
) -> ConnectorField:
    """Sensitive profile value -> secret store; only a reference is persisted."""
    return ConnectorField(
        name=name,
        label=label,
        binding=SECRET_PARAM,
        type=PASSWORD if is_highly_sensitive else TEXT,
        group=group,
        required=required,
        min_length=min_length,
        max_length=max_length,
        help_text=help_text,
        example=example,
        is_highly_sensitive=is_highly_sensitive,
    )


def task_param(
    name: str,
    label: str,
    *,
    type: str = TEXT,
    required: bool = False,
    help_text: str | None = None,
    example: str | None = None,
) -> ConnectorField:
    """Run-time value -> supplied by the BPMN service task; never persisted."""
    return ConnectorField(
        name=name,
        label=label,
        binding=TASK_PARAM,
        type=type,
        group="task",
        required=required,
        help_text=help_text,
        example=example,
    )


@dataclass(frozen=True)
class ValidationError:
    """One field-level problem, shaped like the API error contract."""

    loc: tuple[str, ...]
    msg: str
    type: str

    def to_dict(self) -> dict[str, Any]:
        return {"loc": list(self.loc), "msg": self.msg, "type": self.type}


_TRUTHY = {"true", "1", "yes", "on"}
_FALSEY = {"false", "0", "no", "off"}


class ConnectorDefinition:
    """Base class for a connector's declared schema.

    Subclasses set the ClassVars and are registered with
    :func:`m8flow_backend.connectors.registry.register`.
    """

    connector_type: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    category: ClassVar[str] = "integration"
    icon: ClassVar[str] = "extension"
    # Anchor appended to the connector-proxy README link shown in the UI.
    docs_anchor: ClassVar[str | None] = None
    groups: ClassVar[tuple[FieldGroup, ...]] = ()
    fields: ClassVar[tuple[ConnectorField, ...]] = ()
    # Operation used by "Test connection", e.g. "smtp/SendHTMLEmail". Optional.
    test_operation: ClassVar[str | None] = None

    @classmethod
    def profile_fields(cls) -> tuple[ConnectorField, ...]:
        """Fields a saved profile supplies (config + secret)."""
        return tuple(f for f in cls.fields if f.is_profile_field)

    @classmethod
    def config_fields(cls) -> tuple[ConnectorField, ...]:
        return tuple(f for f in cls.fields if f.binding == CONFIG_PARAM)

    @classmethod
    def secret_fields(cls) -> tuple[ConnectorField, ...]:
        return tuple(f for f in cls.fields if f.binding == SECRET_PARAM)

    @classmethod
    def task_fields(cls) -> tuple[ConnectorField, ...]:
        return tuple(f for f in cls.fields if f.binding == TASK_PARAM)

    @classmethod
    def profile_field_names(cls) -> tuple[str, ...]:
        """Names a profile injects into a connector call.

        Single source of truth for both the modeler (which parameters to hide)
        and the runtime (which parameters to inject).
        """
        return tuple(f.name for f in cls.profile_fields())

    @classmethod
    def field_by_name(cls, name: str) -> ConnectorField | None:
        for connector_field in cls.fields:
            if connector_field.name == name:
                return connector_field
        return None

    @classmethod
    def has_profile_support(cls) -> bool:
        return bool(cls.profile_fields())

    @classmethod
    def validate_profile(
        cls, values: dict[str, Any], *, partial: bool = False
    ) -> tuple[dict[str, Any], list[ValidationError]]:
        """Validate + coerce submitted profile values.

        ``partial`` skips required checks for absent keys, for PATCH semantics.
        Returns the cleaned values (profile fields only) and any errors. Unknown
        keys are dropped rather than rejected, so a stored profile keeps loading
        after a field is removed from a definition.
        """
        cleaned: dict[str, Any] = {}
        errors: list[ValidationError] = []

        for connector_field in cls.profile_fields():
            present = connector_field.name in values
            raw = values.get(connector_field.name)

            if not present:
                if partial:
                    continue
                if connector_field.default is not None:
                    cleaned[connector_field.name] = connector_field.default
                elif connector_field.required:
                    errors.append(_missing(connector_field))
                continue

            if raw is None or (isinstance(raw, str) and raw.strip() == ""):
                if connector_field.required:
                    # Clearing a required field is an error, not a reset.
                    errors.append(_missing(connector_field))
                else:
                    cleaned[connector_field.name] = None
                continue

            coerced, error = _coerce(connector_field, raw)
            if error is not None:
                errors.append(error)
            else:
                cleaned[connector_field.name] = coerced

        return cleaned, errors


def _missing(connector_field: ConnectorField) -> ValidationError:
    return ValidationError(
        loc=(connector_field.name,),
        msg=f"{connector_field.label} is required",
        type="missing",
    )


def _coerce(connector_field: ConnectorField, raw: Any) -> tuple[Any, ValidationError | None]:
    """Coerce one submitted value to the field's declared type."""

    def fail(msg: str, error_type: str) -> tuple[Any, ValidationError]:
        return None, ValidationError(loc=(connector_field.name,), msg=msg, type=error_type)

    value: Any = raw

    if connector_field.type == NUMBER:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            return fail(f"{connector_field.label} must be a number", "int_parsing")
    elif connector_field.type == BOOLEAN:
        if isinstance(raw, bool):
            value = raw
        else:
            token = str(raw).strip().lower()
            if token in _TRUTHY:
                value = True
            elif token in _FALSEY:
                value = False
            else:
                return fail(f"{connector_field.label} must be true or false", "bool_parsing")
    else:
        value = raw if isinstance(raw, str) else str(raw)
        value = value.strip()

    if connector_field.choices:
        # Form posts arrive as strings, so match on the rendered value too and
        # then adopt the choice's own value - the connector expects the port as
        # an int, not "587".
        match = next(
            (
                choice
                for choice in connector_field.choices
                if choice.value == value or str(choice.value) == str(value)
            ),
            None,
        )
        if match is None:
            rendered = ", ".join(str(choice.value) for choice in connector_field.choices)
            return fail(f"{connector_field.label} must be one of: {rendered}", "choice_error")
        value = match.value

    if isinstance(value, str):
        if connector_field.min_length is not None and len(value) < connector_field.min_length:
            return fail(
                f"{connector_field.label} must be at least {connector_field.min_length} characters",
                "too_short",
            )
        if connector_field.max_length is not None and len(value) > connector_field.max_length:
            return fail(
                f"{connector_field.label} must be at most {connector_field.max_length} characters",
                "too_long",
            )

    return value, None


# Groups shared by most definitions; a connector may declare its own instead.
DEFAULT_GROUPS: tuple[FieldGroup, ...] = (
    FieldGroup(id="connection", label="Connection"),
    FieldGroup(id="authentication", label="Authentication"),
)

__all__ = [
    "BOOLEAN",
    "CONFIG_PARAM",
    "DEFAULT_GROUPS",
    "MAX_SECRET_FIELD_NAME_LENGTH",
    "NUMBER",
    "SECRET_KEY_MAX_LENGTH",
    "PASSWORD",
    "SECRET_PARAM",
    "SELECT",
    "TASK_PARAM",
    "TEXT",
    "Choice",
    "ConnectorDefinition",
    "ConnectorField",
    "FieldGroup",
    "ValidationError",
    "config_param",
    "secret_param",
    "secret_ref",
    "task_param",
]
