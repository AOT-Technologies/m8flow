"""Rules the profile service applies before anything touches the database."""

from m8flow_backend.connectors.registry import get_connector
from m8flow_backend.services.connector_profile_service import ConnectorProfileService


def _smtp():
    return get_connector("smtp")


def test_config_and_secret_values_are_routed_separately():
    cleaned, errors = _smtp().validate_profile(
        {
            "smtp_host": "smtp.example.com",
            "smtp_user": "svc",
            "smtp_password": "hunter2",
        }
    )
    assert errors == []

    config_values, secret_values = ConnectorProfileService._split(_smtp(), cleaned)

    # Only non-sensitive values may land on the configuration row.
    assert set(secret_values) == {"smtp_user", "smtp_password"}
    assert "smtp_password" not in config_values
    assert config_values["smtp_host"] == "smtp.example.com"


def test_a_blank_secret_on_update_keeps_the_stored_value():
    """The edit form posts a blank box for any secret the user did not retype."""
    submitted = {"smtp_host": "smtp.example.com", "smtp_password": "   "}

    kept = ConnectorProfileService._drop_untouched_secrets(_smtp(), submitted)

    assert "smtp_password" not in kept
    assert kept["smtp_host"] == "smtp.example.com"


def test_an_explicit_null_secret_is_a_clear_not_a_keep():
    submitted = {"smtp_password": None}

    kept = ConnectorProfileService._drop_untouched_secrets(_smtp(), submitted)

    assert kept == {"smtp_password": None}


def test_a_blank_non_secret_field_is_left_for_validation():
    submitted = {"smtp_host": ""}

    kept = ConnectorProfileService._drop_untouched_secrets(_smtp(), submitted)

    assert kept == {"smtp_host": ""}
