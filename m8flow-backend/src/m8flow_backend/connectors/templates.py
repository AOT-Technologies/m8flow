"""Registered connector templates: the HTTP family plus the m8flow connectors.

A template is what makes a connector configurable -- the profiles page and
profile validation both reject a connector_type that is not registered here.
Listing in the Connectors tab is separate, driven by the proxy catalogue.
"""

from __future__ import annotations

from typing import Any

from m8flow_backend.connectors.http_template import CONNECTOR_TYPE, http_descriptor
from m8flow_backend.connectors.m8flow_templates import M8FLOW_DESCRIPTORS

_TEMPLATES: dict[str, dict[str, Any]] = {
    CONNECTOR_TYPE: http_descriptor(),
    **{descriptor["id"]: descriptor for descriptor in M8FLOW_DESCRIPTORS},
}


def all_templates() -> list[dict[str, Any]]:
    return [dict(item) for item in _TEMPLATES.values()]


def template_for(connector_type: str) -> dict[str, Any] | None:
    found = _TEMPLATES.get(connector_type)
    return dict(found) if found is not None else None


def known_connector_type(connector_type: str) -> bool:
    return connector_type in _TEMPLATES


def secret_field_names(connector_type: str) -> frozenset[str]:
    """Fields whose values require secret-provider storage.

    ``isHighlySensitive`` is the canonical field-level signal. Older
    descriptors without it remain protected when they mark a field ``secret``
    or use a password input. Password inputs always stay sensitive.
    """
    template = _TEMPLATES.get(connector_type)
    if template is None:
        return frozenset()
    return frozenset(
        str(field["id"])
        for field in template.get("profileFields", [])
        if field.get("type") == "password"
        or field.get("isHighlySensitive", field.get("secret", False)) is True
    )
