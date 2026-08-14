"""Validation and coercion of submitted profile values."""

from m8flow_backend.connectors.registry import get_connector


def _smtp():
    return get_connector("smtp")


def test_required_fields_are_reported_by_name():
    cleaned, errors = _smtp().validate_profile({"smtp_port": 587})

    assert cleaned.get("smtp_port") == 587
    locations = {tuple(error.loc) for error in errors}
    assert ("smtp_host",) in locations
    # Optional on the command, so optional here.
    assert ("smtp_user",) not in locations
    assert ("smtp_password",) not in locations


def test_values_are_coerced_to_their_declared_types():
    cleaned, errors = _smtp().validate_profile(
        {
            "smtp_host": "  smtp.example.com  ",
            "smtp_port": "465",
            "smtp_starttls": "false",
            "smtp_password": "hunter2",
        }
    )

    assert errors == []
    assert cleaned["smtp_host"] == "smtp.example.com"
    assert cleaned["smtp_port"] == 465
    assert cleaned["smtp_starttls"] is False
    assert cleaned["smtp_password"] == "hunter2"


def test_a_value_outside_the_declared_choices_is_rejected():
    _cleaned, errors = _smtp().validate_profile(
        {"smtp_host": "smtp.example.com", "smtp_port": 2525}
    )

    assert [tuple(error.loc) for error in errors] == [("smtp_port",)]
    assert errors[0].type == "choice_error"


def test_partial_validation_ignores_absent_fields():
    cleaned, errors = _smtp().validate_profile({"smtp_host": "relay.example.com"}, partial=True)

    assert errors == []
    assert cleaned == {"smtp_host": "relay.example.com"}


def test_defaults_are_applied_when_a_field_is_omitted():
    cleaned, _errors = _smtp().validate_profile({"smtp_host": "smtp.example.com"})

    assert cleaned["smtp_port"] == 587
    assert cleaned["smtp_starttls"] is True


def test_unknown_keys_are_dropped_rather_than_rejected():
    cleaned, errors = _smtp().validate_profile(
        {"smtp_host": "smtp.example.com", "removed_field": "x"}
    )

    assert errors == []
    assert "removed_field" not in cleaned
