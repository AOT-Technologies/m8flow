"""Two-phase validation (M8Flow.md 4.7).

A definition mixes fields with two lifecycles. ``config_param``/``secret_param``
values exist when a tenant saves a profile; ``task_param`` values exist only
when a workflow runs. Validating everything at save time would fail on runtime
fields that cannot exist yet, so validation is split:

phase 1, profile save
    the *connection model* -- the non-``task_param`` subset.
phase 2, execution
    the full model, over config + secrets + resolved task params.

No placeholders and no dummy values: a bad task parameter surfaces in phase 2
as a field error on the service task, never silently.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from m8flow_backend.connectors.base import (
    PROFILE_BINDINGS,
    TASK_PARAM,
    ConnectorDefinition,
    unwrap_annotation,
)


def _model_for(cls: type[ConnectorDefinition], bindings: tuple[str, ...], suffix: str) -> type[BaseModel]:
    """A submodel over the fields whose binding is in ``bindings``.

    Requiredness is re-applied here rather than inherited: on the definition
    every field is optional so a phase-1 payload may omit runtime fields, so
    the phase model is what actually enforces "required".
    """
    fields: dict[str, Any] = {}
    for name, field in cls.model_fields.items():
        extra = field.json_schema_extra or {}
        if extra.get("binding") not in bindings:
            continue
        _, optional, _ = unwrap_annotation(field.annotation)
        # A declared default makes a field satisfiable without input, so it is
        # not required even when its annotation is non-optional.
        default = extra.get("default_value")
        required = bool(extra.get("required", not optional and default is None))
        if required:
            placeholder: Any = ...
        elif default is not None:
            placeholder = default
        else:
            placeholder = None
        fields[name] = (field.annotation, placeholder)

    # extra="forbid" so a payload naming an unknown field -- or a task_param at
    # phase 1 -- is rejected as such, instead of surfacing as a confusing
    # "field required" on some other field.
    return create_model(
        f"{cls.__name__}{suffix}",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


@lru_cache(maxsize=None)
def connection_model(cls: type[ConnectorDefinition]) -> type[BaseModel]:
    """Phase-1 model: the profile fields only."""
    return _model_for(cls, PROFILE_BINDINGS, "Connection")


@lru_cache(maxsize=None)
def runtime_model(cls: type[ConnectorDefinition]) -> type[BaseModel]:
    """Phase-2 model: profile fields plus task params."""
    return _model_for(cls, (*PROFILE_BINDINGS, TASK_PARAM), "Runtime")


def errors_to_api_shape(error: ValidationError, *, prefix: str = "config") -> list[dict[str, Any]]:
    """Pydantic errors in the API's error contract (M8Flow.md 8)."""
    return [
        {
            "loc": [prefix, *(str(part) for part in item["loc"])],
            "msg": item["msg"],
            "type": item["type"],
        }
        for item in error.errors()
    ]


def _coerce_scalars(
    cls: type[ConnectorDefinition], values: dict[str, Any]
) -> dict[str, Any]:
    """Coerce string input to the declared scalar type before validation.

    Every value reaching this layer is a string: HTML form fields submit strings,
    and secret-store values come back as text. Without this, an int or bool field
    -- and especially a Literal like smtp_port's 25/587/465 -- would reject "587"
    outright, so a whole profile would fail to save over a type the user could
    not see or fix.
    """
    coerced = dict(values)
    for name, value in values.items():
        if not isinstance(value, str):
            continue
        field = cls.model_fields.get(name)
        if field is None:
            continue
        annotation, _, _ = unwrap_annotation(field.annotation)
        text = value.strip()
        if text == "":
            continue
        try:
            if annotation is bool:
                lowered = text.lower()
                if lowered in ("true", "yes", "on", "1"):
                    coerced[name] = True
                elif lowered in ("false", "no", "off", "0"):
                    coerced[name] = False
            elif annotation is int:
                coerced[name] = int(text)
            elif annotation is float:
                coerced[name] = float(text)
        except ValueError:
            # Leave it as the string it was: pydantic will report a type error
            # against the field, which is a clearer message than anything here.
            pass
    return coerced


def validate_profile(
    cls: type[ConnectorDefinition], values: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Phase-1 validate a profile payload.

    Returns ``(cleaned, errors)``. Unset optional fields are dropped rather
    than stored as null, so a profile only carries what was actually filled in
    and a blank optional never overrides a task-level value at runtime.
    """
    try:
        validated = connection_model(cls).model_validate(_coerce_scalars(cls, values))
    except ValidationError as error:
        return ({}, errors_to_api_shape(error))

    cleaned = {
        name: value
        for name, value in validated.model_dump().items()
        if value is not None and value != ""
    }
    return (cleaned, [])
