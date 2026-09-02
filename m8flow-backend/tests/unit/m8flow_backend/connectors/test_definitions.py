"""The connector definitions, their descriptors, and both validation phases."""

from __future__ import annotations

from urllib.parse import quote

import pytest

from m8flow_backend.connectors.base import (
    MAX_SECRET_FIELD_NAME_LENGTH,
    SECRET_KEY_MAX_LENGTH,
    SECRET_PARAM,
    TASK_PARAM,
    secret_ref,
)
from m8flow_backend.connectors.descriptor import to_descriptor
from m8flow_backend.connectors.registry import all_connectors, get_connector
from m8flow_backend.connectors.validation import (
    connection_model,
    runtime_model,
    validate_profile,
)

EXPECTED_CONNECTORS = {
    "github",
    "http",
    "n8n",
    "postgres_v2",
    "salesforce",
    "slack",
    "smtp",
    "stripe",
}


def test_all_eight_connectors_are_registered():
    assert {cls.connector_type for cls in all_connectors()} == EXPECTED_CONNECTORS


def test_unknown_connector_type_resolves_to_none():
    assert get_connector("not-a-connector") is None


@pytest.mark.parametrize("connector_type", sorted(EXPECTED_CONNECTORS))
def test_descriptor_shape(connector_type):
    descriptor = to_descriptor(get_connector(connector_type))

    assert descriptor["id"] == connector_type
    assert descriptor["name"]
    assert descriptor["schemaVersion"] == "1"
    assert descriptor["supportsProfiles"] is True
    # Every connector must offer something a profile can hold, or it has no
    # business appearing in the profile UI at all.
    assert descriptor["profileFields"]

    for field in descriptor["profileFields"] + descriptor["taskFields"]:
        assert field["id"]
        assert field["label"]
        # The frontend validator only understands this vocabulary.
        assert field["type"] in {"text", "password", "number", "boolean", "select", "textarea"}
        assert isinstance(field["required"], bool)
        assert field["sensitive"] is field["secret"]
        assert "isHighlySensitive" not in field


@pytest.mark.parametrize("connector_type", sorted(EXPECTED_CONNECTORS))
def test_descriptor_never_leaks_a_field_into_both_buckets(connector_type):
    descriptor = to_descriptor(get_connector(connector_type))
    profile_ids = {field["id"] for field in descriptor["profileFields"]}
    task_ids = {field["id"] for field in descriptor["taskFields"]}
    assert not (profile_ids & task_ids)


@pytest.mark.parametrize("connector_type", sorted(EXPECTED_CONNECTORS))
def test_every_profile_field_belongs_to_a_declared_group(connector_type):
    definition = get_connector(connector_type)
    declared = {group["id"] for group in definition.groups}
    descriptor = to_descriptor(definition)
    for field in descriptor["profileFields"]:
        assert field["group"] in declared, field["id"]


@pytest.mark.parametrize("connector_type", sorted(EXPECTED_CONNECTORS))
def test_secret_keys_fit_the_upstream_key_column(connector_type):
    """Secret keys must fit upstream's VARCHAR(50) secret.key column.

    Widening an upstream table is out of bounds, so the budget is a hard
    constraint on field names rather than something to fix later.
    """
    definition = get_connector(connector_type)
    for name in definition.secret_field_names():
        assert len(name) <= MAX_SECRET_FIELD_NAME_LENGTH
        # 9999999999 is the largest configuration id the budget allows for.
        assert len(secret_ref(9999999999, name)) <= SECRET_KEY_MAX_LENGTH


def test_secret_ref_is_keyed_on_configuration_id_not_profile_name():
    """Renaming a profile must not move its secrets."""
    assert secret_ref(17, "smtp_password") == "cnx.17.smtp_password"


def test_secret_ref_is_a_single_url_path_segment():
    """A secret key is addressed as /secrets/{key}, one path segment.

    WSGI decodes %2F back into PATH_INFO before routing, so a key containing
    "/" is unreachable however the frontend encodes it -- show, update and
    delete all 404. Keep the ref free of path separators.
    """
    key = secret_ref(9999999999, "smtp_password")
    assert "/" not in key
    assert quote(key, safe="") == key


@pytest.mark.parametrize("connector_type", sorted(EXPECTED_CONNECTORS))
def test_task_params_are_never_stored_in_a_profile(connector_type):
    definition = get_connector(connector_type)
    profile_names = set(definition.profile_field_names())
    for name, field in definition.model_fields.items():
        binding = (field.json_schema_extra or {}).get("binding")
        if binding == TASK_PARAM:
            assert name not in profile_names


# ---------------------------------------------------------------- phase 1


def test_phase_one_accepts_a_valid_profile_and_applies_defaults():
    cleaned, errors = validate_profile(
        get_connector("smtp"),
        {"smtp_host": "smtp.gmail.com", "smtp_password": "pw"},
    )
    assert errors == []
    assert cleaned["smtp_host"] == "smtp.gmail.com"
    # Declared defaults are materialised so the stored profile is complete.
    assert cleaned["smtp_port"] == 587


def test_phase_one_reports_a_missing_required_field():
    _, errors = validate_profile(get_connector("smtp"), {"smtp_password": "pw"})
    assert errors == [
        {"loc": ["config", "smtp_host"], "msg": "Field required", "type": "missing"}
    ]


def test_phase_one_rejects_a_value_outside_the_declared_choices():
    _, errors = validate_profile(
        get_connector("smtp"), {"smtp_host": "h", "smtp_port": 2525}
    )
    assert errors[0]["loc"] == ["config", "smtp_port"]
    assert errors[0]["type"] == "literal_error"


def test_phase_one_rejects_a_task_param():
    """Runtime fields cannot be saved into a profile.

    Without this they would be silently dropped, and an author would think a
    per-task value had been stored tenant-wide.
    """
    _, errors = validate_profile(
        get_connector("smtp"), {"smtp_host": "h", "email_to": "a@b.com"}
    )
    assert errors[0]["loc"] == ["config", "email_to"]
    assert errors[0]["type"] == "extra_forbidden"


def test_phase_one_rejects_an_unknown_field():
    _, errors = validate_profile(
        get_connector("smtp"), {"smtp_host": "h", "not_a_field": "x"}
    )
    assert errors[0]["type"] == "extra_forbidden"


def test_phase_one_drops_blanks_so_they_cannot_shadow_a_task_value():
    """An unfilled optional must not be stored.

    A stored empty string would count as "set" at runtime and would stop the
    author's task-level value from being used.
    """
    cleaned, errors = validate_profile(
        get_connector("slack"), {"token": "xoxb-1", "channel": ""}
    )
    assert errors == []
    assert "channel" not in cleaned


def test_connection_model_excludes_task_params():
    fields = connection_model(get_connector("smtp")).model_fields
    assert "smtp_host" in fields
    assert "smtp_password" in fields
    assert "email_to" not in fields


# ---------------------------------------------------------------- phase 2


def test_phase_two_validates_task_params():
    model = runtime_model(get_connector("smtp"))
    validated = model.model_validate(
        {
            "smtp_host": "h",
            "smtp_port": 587,
            "smtp_password": "pw",
            "email_to": "a@b.com",
            "email_subject": "hello",
        }
    )
    assert validated.email_to == "a@b.com"


def test_phase_two_reports_a_missing_task_param():
    import pydantic

    with pytest.raises(pydantic.ValidationError) as caught:
        runtime_model(get_connector("smtp")).model_validate(
            {"smtp_host": "h", "email_subject": "s"}
        )
    missing = {error["loc"][0] for error in caught.value.errors()}
    assert "email_to" in missing


# ------------------------------------------------------- connector specifics


def test_postgres_credential_is_a_single_secret_connection_string():
    """The shipped connector takes one connection string, not host/user/pass.

    The design note illustrates pg_host/pg_password, which do not exist in the
    real connector; this guards the discrepancy.
    """
    definition = get_connector("postgres_v2")
    assert definition.secret_field_names() == ("database_connection_str",)


def test_salesforce_carries_the_full_refresh_credential_set():
    definition = get_connector("salesforce")
    assert set(definition.secret_field_names()) == {
        "instance_url",
        "access_token",
        "refresh_token",
        "client_id",
        "client_secret",
    }


def test_n8n_holds_both_credential_styles_in_one_profile():
    """The webhook and API operators need disjoint credentials.

    Both live in one profile; the runtime patch injects only what the chosen
    operator declares, so the webhook operator never receives an api_key.
    """
    definition = get_connector("n8n")
    profile_fields = set(definition.profile_field_names())
    assert {"base_url", "api_key"} <= profile_fields
    assert "webhook_url" not in profile_fields


def test_slack_token_is_the_secret_and_channel_is_not():
    definition = get_connector("slack")
    assert definition.field_binding("token") == SECRET_PARAM
    assert definition.field_binding("channel") != SECRET_PARAM
    assert definition.field_is_sensitive("token") is True
    assert definition.field_is_sensitive("channel") is False


# ------------------------------------------------- string input coercion


def test_a_string_port_from_a_form_is_accepted():
    """Form fields and secret-store values both arrive as strings.

    Without coercion a Literal[25, 587, 465] would reject "587", so a whole
    profile would fail to save over a type the user cannot see or fix.
    """
    cleaned, errors = validate_profile(
        get_connector("smtp"),
        {"smtp_host": "h", "smtp_port": "587", "smtp_password": "p"},
    )
    assert errors == []
    assert cleaned["smtp_port"] == 587


@pytest.mark.parametrize(
    "raw,expected",
    [("true", True), ("True", True), ("on", True), ("1", True),
     ("false", False), ("no", False), ("0", False)],
)
def test_a_string_boolean_is_coerced(raw, expected):
    cleaned, errors = validate_profile(
        get_connector("smtp"),
        {"smtp_host": "h", "smtp_starttls": raw, "smtp_password": "p"},
    )
    assert errors == []
    assert cleaned.get("smtp_starttls", False) is expected


@pytest.mark.parametrize("raw", ["9999", "abc", "-1"])
def test_coercion_still_rejects_an_invalid_value(raw):
    """Coercion must not become a way to smuggle a bad value through."""
    _, errors = validate_profile(
        get_connector("smtp"), {"smtp_host": "h", "smtp_port": raw}
    )
    assert errors
    assert errors[0]["loc"] == ["config", "smtp_port"]


# --------------------------------------------- the proxy field-name contract

# Parameter ids taken from m8flow-connector-proxy/README.md and cross-checked
# against the shipped sample templates' BPMN. The proxy builds each command as
# command(**params), so a name outside this set is silently never sent.
#
# The live check is `bin/check-connector-fields.py`, which reads GET /v1/commands
# from a running proxy. This test is the offline guard that catches a typo or a
# rename in review, without needing the proxy up.
VERIFIED_PARAMETER_NAMES = {
    "smtp": {
        "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_starttls",
        "email_to", "email_subject", "email_body", "email_body_html", "email_cc",
        "email_bcc", "email_reply_to", "email_from", "attachments",
    },
    "slack": {
        "token", "channel", "user_id", "message", "blocks", "filepath",
        "content_base64",
    },
    "postgres_v2": {"database_connection_str", "table_name", "schema"},
    "salesforce": {
        "access_token", "instance_url", "refresh_token", "client_id",
        "client_secret", "record_id", "fields",
    },
    "http": {
        "url", "headers", "params", "data", "basic_auth_username",
        "basic_auth_password",
    },
    "stripe": {
        "api_key", "amount", "currency", "source", "customer_id", "price_id",
        "subscription_id", "idempotency_key",
    },
    "n8n": {
        "webhook_url", "method", "payload", "auth_type", "auth_header_name",
        "auth_header_value", "username", "password", "base_url", "api_key",
        "active", "limit", "cursor", "workflow_id", "status", "execution_id",
        "include_data",
    },
}


@pytest.mark.parametrize("connector_type", sorted(VERIFIED_PARAMETER_NAMES))
def test_field_names_are_real_proxy_parameters(connector_type):
    definition = get_connector(connector_type)
    declared = {definition.wire_name(name) for name in definition.model_fields}
    unknown = declared - VERIFIED_PARAMETER_NAMES[connector_type]
    assert not unknown, (
        f"{connector_type} declares {sorted(unknown)}, which the connector does "
        f"not accept. The proxy calls command(**params), so these would never "
        f"be sent."
    )


def test_github_is_the_only_connector_with_unverified_names():
    """A reminder, not a rule to work around.

    GitHub has no README section and no sample template, so its proxy keyword
    arguments could not be confirmed offline. If another connector ends up here,
    verify it against a running proxy instead of widening this test.
    """
    unverified = {
        cls.connector_type
        for cls in all_connectors()
        if cls.connector_type not in VERIFIED_PARAMETER_NAMES
    }
    assert unverified == {"github"}
