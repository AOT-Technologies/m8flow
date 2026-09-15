"""Registered connector templates. HTTP is the only family in keep-scope."""

from __future__ import annotations

from typing import Any

from m8flow_backend.connectors.http_template import CONNECTOR_TYPE, http_descriptor

_TEMPLATES: dict[str, dict[str, Any]] = {CONNECTOR_TYPE: http_descriptor()}


def all_templates() -> list[dict[str, Any]]:
    return [dict(item) for item in _TEMPLATES.values()]


def template_for(connector_type: str) -> dict[str, Any] | None:
    found = _TEMPLATES.get(connector_type)
    return dict(found) if found is not None else None


def known_connector_type(connector_type: str) -> bool:
    return connector_type in _TEMPLATES


def secret_field_names(connector_type: str) -> frozenset[str]:
    template = _TEMPLATES.get(connector_type)
    if template is None:
        return frozenset()
    return frozenset(
        str(field["id"])
        for field in template.get("profileFields", [])
        if field.get("secret")
    )
