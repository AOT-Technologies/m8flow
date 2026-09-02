"""Preparation and validation for connector profile document storage.

This module is intentionally independent from the current profile CRUD service.
It provides the target storage shape while the legacy key/value provider is
still active. The cutover service can use these helpers atomically when a
document-capable provider is configured.
"""

from __future__ import annotations

from typing import Any
from m8flow_backend.connectors.base import SECRET_PARAM, ConnectorDefinition
from m8flow_backend.models.connector_configuration import (
    ConnectorConfigurationModel,
    ConnectorVariableModel,
)
from m8flow_backend.services.connector_secret_backend import document_backend
from m8flow_backend.services.vault_path_utils import (
    vault_safe_tenant_path_component,
)
from spiffworkflow_backend.models.db import db


def provider_key(tenant_id: str, connector_configuration_id: int) -> str:
    """Build the immutable document identifier for one connector profile.

    The tenant namespace is part of the logical key because the tenant AppRole
    policy permits only this subtree. The database id is used instead of the
    mutable profile name so renaming cannot move or orphan the document.
    """
    tenant_component = vault_safe_tenant_path_component(tenant_id)
    if not isinstance(connector_configuration_id, int) or connector_configuration_id <= 0:
        raise ValueError("connector_configuration_id must be a positive integer.")
    return (
        f"tenants/{tenant_component}/secrets/connector-configuration/"
        f"{connector_configuration_id}"
    )


def secret_document(
    definition: type[ConnectorDefinition], values: dict[str, Any]
) -> dict[str, str]:
    """Return only sensitive profile values for the provider document."""
    secret_names = set(definition.secret_field_names())
    unknown = set(values) - secret_names
    if unknown:
        raise ValueError(
            "Connector secret document contains non-sensitive fields: "
            + ", ".join(sorted(unknown))
        )
    return {
        name.upper(): str(value)
        for name, value in values.items()
        if value not in (None, "")
    }


def variable_rows(
    profile: ConnectorConfigurationModel,
    definition: type[ConnectorDefinition],
    values: dict[str, Any],
    user_id: int | None,
) -> list[ConnectorVariableModel]:
    """Build database metadata rows without placing sensitive values in them."""
    rows: list[ConnectorVariableModel] = []
    for name in definition.profile_field_names():
        sensitive = definition.field_binding(name) == SECRET_PARAM
        raw_value = values.get(name)
        rows.append(
            ConnectorVariableModel(
                m8f_tenant_id=profile.m8f_tenant_id,
                connector_configuration_id=profile.id,
                field_name=name,
                is_sensitive=sensitive,
                value=None if sensitive else raw_value,
                is_configured=(raw_value not in (None, "")) if sensitive else False,
                user_id=user_id,
            )
        )
    return rows


def prepare_profile_storage(
    profile: ConnectorConfigurationModel,
    definition: type[ConnectorDefinition],
    config_values: dict[str, Any],
    secret_values: dict[str, Any],
    user_id: int | None,
) -> tuple[str, list[ConnectorVariableModel], dict[str, str]]:
    """Prepare provider key, metadata rows, and secret document for a profile."""
    if not profile.id or not profile.m8f_tenant_id:
        raise ValueError("A persisted tenant-bound profile is required.")
    document = secret_document(definition, secret_values)
    combined_values = {**config_values, **secret_values}
    return (
        provider_key(profile.m8f_tenant_id, profile.id),
        variable_rows(profile, definition, combined_values, user_id),
        document,
    )


def persist_profile_document(
    profile: ConnectorConfigurationModel,
    definition: type[ConnectorDefinition],
    config_values: dict[str, Any],
    secret_values: dict[str, Any],
    user_id: int | None,
) -> str | None:
    """Persist a new profile document and its non-secret metadata atomically.

    The provider write happens before the database commit because the database
    row must never point at a document that was not created. If the commit
    fails, the best-effort provider delete leaves no reachable credential
    document. This operation is explicit and is not called by legacy CRUD.
    """
    backend = document_backend()
    key, rows, document = prepare_profile_storage(
        profile, definition, config_values, secret_values, user_id
    )
    try:
        version = backend.write_document(key, document, user_id)
        profile.provider_key = key
        profile.schema_version = definition.schema_version
        db.session.add_all(rows)
        db.session.commit()
        return version
    except Exception:
        db.session.rollback()
        try:
            backend.delete_document(key)
        except Exception:
            # The profile is not committed, so a failed cleanup is an
            # unreachable provider orphan for the reconciliation job.
            pass
        raise
