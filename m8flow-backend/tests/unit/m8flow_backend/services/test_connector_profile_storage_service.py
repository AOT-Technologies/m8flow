"""Tests for connector document storage preparation."""

from __future__ import annotations

import pytest

from m8flow_backend.connectors.registry import get_connector
from m8flow_backend.services.connector_profile_storage_service import (
    prepare_profile_storage,
    provider_key,
    secret_document,
    variable_rows,
)


class _Profile:
    id = 17
    m8f_tenant_id = "tenant/one"
    profile_name = "slack-profile"


def test_provider_key_is_immutable_and_tenant_scoped():
    assert provider_key("tenant/one", 17) == "tenants/tenant%2Fone/secrets/connector-configuration/17"
    assert provider_key("tenant/one", 17) == provider_key("tenant/one", 17)


def test_secret_document_rejects_non_sensitive_values():
    definition = get_connector("smtp")

    with pytest.raises(ValueError, match="non-sensitive fields"):
        secret_document(definition, {"smtp_host": "smtp.example.com"})


def test_variable_rows_never_store_sensitive_values():
    definition = get_connector("smtp")

    rows = variable_rows(
        _Profile(),
        definition,
        {"smtp_host": "smtp.example.com", "smtp_password": "hunter2"},
        7,
    )
    by_name = {row.field_name: row for row in rows}

    assert by_name["smtp_password"].is_sensitive is True
    assert by_name["smtp_password"].value is None
    assert by_name["smtp_password"].is_configured is True
    assert by_name["smtp_host"].value == "smtp.example.com"


def test_prepare_storage_returns_one_document_and_metadata_rows():
    definition = get_connector("slack")
    key, rows, document = prepare_profile_storage(
        _Profile(), definition, {"channel": "alerts"}, {"token": "secret"}, 7
    )

    assert key == "tenants/tenant%2Fone/secrets/connector-configuration/17"
    assert document == {"TOKEN": "secret"}
    assert len(rows) == len(definition.profile_field_names())
    assert all(row.value != "secret" for row in rows)
