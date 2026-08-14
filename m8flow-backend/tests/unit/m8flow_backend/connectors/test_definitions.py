"""The connector definitions are a contract with the connector proxy.

A profile field name IS the keyword argument the proxy passes to the connector
command, so these tests pin the names down: a rename that is not matched in the
connector package silently stops a profile from supplying that value.
"""

import pytest

from m8flow_backend.connectors.base import (
    MAX_SECRET_FIELD_NAME_LENGTH,
    SECRET_KEY_MAX_LENGTH,
    ConnectorDefinition,
    config_param,
    secret_param,
    secret_ref,
)
from m8flow_backend.connectors.descriptor import to_descriptor
from m8flow_backend.connectors.registry import all_connectors, get_connector, register

# Field names verified against the command signatures in the m8flow-connectors
# packages and the shipped sample templates.
EXPECTED_PROFILE_FIELDS = {
    "smtp": {"smtp_host", "smtp_port", "smtp_starttls", "email_from", "smtp_user", "smtp_password"},
    "slack": {"token"},
    "github": {"token"},
    "salesforce": {"instance_url", "client_id", "client_secret", "access_token", "refresh_token"},
    "stripe": {"api_key"},
    "n8n": {"base_url", "api_key"},
    "postgres_v2": {"database_connection_str"},
    "http": set(),
}


def test_every_expected_connector_is_registered():
    registered = {definition.connector_type for definition in all_connectors()}
    assert registered == set(EXPECTED_PROFILE_FIELDS)


@pytest.mark.parametrize("connector_type,expected", sorted(EXPECTED_PROFILE_FIELDS.items()))
def test_profile_field_names_match_the_connector_commands(connector_type, expected):
    definition = get_connector(connector_type)
    assert set(definition.profile_field_names()) == expected


def test_connectors_without_profile_fields_do_not_offer_profiles():
    assert get_connector("http").has_profile_support() is False
    assert get_connector("smtp").has_profile_support() is True


def test_descriptor_shape_for_smtp():
    descriptor = to_descriptor(get_connector("smtp"))

    assert descriptor["id"] == "smtp"
    assert descriptor["name"] == "SMTP"
    assert descriptor["supportsProfiles"] is True

    fields = {field["id"]: field for field in descriptor["profileFields"]}
    assert fields["smtp_password"]["type"] == "password"
    assert fields["smtp_password"]["secret"] is True
    assert fields["smtp_host"]["secret"] is False
    assert fields["smtp_port"]["default"] == 587
    assert [choice["value"] for choice in fields["smtp_port"]["choices"]] == [25, 587, 465]


def test_no_descriptor_leaks_a_value():
    """Descriptors describe shape only."""
    for definition in all_connectors():
        for field in to_descriptor(definition)["profileFields"]:
            assert "value" not in field


def test_secret_keys_fit_the_secret_store():
    for definition in all_connectors():
        for field in definition.secret_fields():
            key = secret_ref(9999999999, field.name)
            assert len(key) <= SECRET_KEY_MAX_LENGTH, key


def test_registry_rejects_a_secret_field_name_that_would_not_fit():
    class OverlongConnector(ConnectorDefinition):
        connector_type = "overlong_test"
        display_name = "Overlong"
        fields = (secret_param("x" * (MAX_SECRET_FIELD_NAME_LENGTH + 1), "Too long"),)

    with pytest.raises(ValueError, match="too long"):
        register(OverlongConnector)


def test_registry_rejects_duplicate_field_names():
    class DuplicateConnector(ConnectorDefinition):
        connector_type = "duplicate_test"
        display_name = "Duplicate"
        fields = (
            config_param("host", "Host"),
            config_param("host", "Host again"),
        )

    with pytest.raises(ValueError, match="duplicate field names"):
        register(DuplicateConnector)
