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


def profile_fields(connector_type: str) -> dict[str, dict[str, Any]]:
    """Profile fields by id. Every one is stored as a tenant secret."""
    template = _TEMPLATES.get(connector_type) or {}
    return {
        str(field["id"]): field
        for field in template.get("profileFields", [])
        if field.get("secret")
    }


def secret_field_names(connector_type: str) -> frozenset[str]:
    return frozenset(profile_fields(connector_type))


def plain_field_names(connector_type: str) -> frozenset[str]:
    """Stored fields that are configuration, not credentials (host, port, URL…).

    Only these are ever read back to the profile form. Opt-in: a field must be
    marked ``prefill: True``, so a template that forgets a flag stays write-only.
    The sensitivity checks are a second guard against a mis-marked credential.
    """
    return frozenset(
        name
        for name, field in profile_fields(connector_type).items()
        if field.get("prefill") is True
        and field.get("isHighlySensitive") is False
        and field.get("type") != "password"
    )
