"""Metadata contract for the Connectors tab.

The tab is built entirely from the connector-proxy catalogue, so a connector
the proxy serves but this metadata does not name still gets a card -- just a
humanized fallback name and no Configure form. These tests pin the parts that
fail silently: a missing profiles flag hides the profiles page, and a config
field whose Secret key the runtime resolver cannot match is dropped.
"""

from __future__ import annotations

from m8flow_backend.routes.connectors_controller import (
    CONNECTOR_METADATA,
    effective_secret_key,
    format_operation_name,
    _valid_config_fields,
)

# The connector keys the m8flow-node-wire-proxy catalogue serves. Kept here as
# a literal rather than imported: the proxy is a separate package, and the
# point is to notice when the two drift apart.
_PROXY_CONNECTOR_KEYS = {
    "http",
    "github",
    "n8n",
    "smtp",
    "slack",
    "salesforce",
    "stripe",
    "postgres_v2",
}


def test_every_proxy_connector_has_display_metadata() -> None:
    """Without an entry a card falls back to a humanized id and no icon."""
    assert _PROXY_CONNECTOR_KEYS <= set(CONNECTOR_METADATA)


def test_every_connector_offers_profiles() -> None:
    """supportsProfiles is what renders the "Saved credential sets" page."""
    for key in _PROXY_CONNECTOR_KEYS:
        assert CONNECTOR_METADATA[key].get("supportsProfiles") is True, key


def test_every_config_field_survives_secret_key_validation() -> None:
    """A field whose effective key is not \\w+ is silently dropped from the form."""
    for key, meta in CONNECTOR_METADATA.items():
        declared = meta.get("configFields", [])
        assert _valid_config_fields(key, declared) == declared, key


def test_config_fields_resolve_to_distinct_secret_keys() -> None:
    """Two fields sharing a Secret key would overwrite each other on save."""
    for key, meta in CONNECTOR_METADATA.items():
        fields = meta.get("configFields", [])
        resolved = [effective_secret_key(key, field) for field in fields]
        assert len(resolved) == len(set(resolved)), key


def test_metadata_entries_carry_the_fields_the_card_renders() -> None:
    for key, meta in CONNECTOR_METADATA.items():
        assert meta.get("name"), key
        assert meta.get("description"), key
        assert meta.get("icon"), key


def test_pascal_case_operation_names_render_as_words() -> None:
    """The proxy catalogue names m8flow actions in PascalCase for this reason:
    a snake_case name would render as one lowercase word."""
    assert format_operation_name("ConnectRepository") == "Connect Repository"
    assert format_operation_name("ListPullRequests") == "List Pull Requests"
    assert format_operation_name("SendDirectMessage") == "Send Direct Message"
    assert format_operation_name("GetRequestV2") == "Get Request"
    # SMTP is an abbreviation the formatter must not title-case.
    assert format_operation_name("SendSMTPEmail") == "Send SMTP Email"


def test_every_template_field_is_a_parameter_the_proxy_accepts() -> None:
    """The silent-failure guard.

    Profile injection fills only parameters the proxy catalogue declares, and
    only when the task left them empty. A profile field whose id is not such a
    parameter is simply never sent -- no error, just a confusing auth failure
    from the remote system later. These names are transcribed from
    m8flow-node-wire-proxy's catalog.py, which mirrors each connector's model.
    """
    from m8flow_backend.connectors.m8flow_templates import M8FLOW_DESCRIPTORS

    accepted = {
        "github": {"token", "owner", "repo", "per_page", "page", "protected", "state"},
        "n8n": {
            "base_url", "api_key", "webhook_url", "method", "payload", "auth_type",
            "auth_header_name", "auth_header_value", "username", "password",
            "workflow_id", "execution_id", "include_data", "status", "limit", "cursor",
        },
        "smtp": {
            "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_starttls",
            "email_from", "email_to", "email_subject", "email_body", "email_body_html",
            "email_cc", "email_bcc", "email_reply_to", "attachments",
        },
        "slack": {
            "token", "channel", "user_id", "message", "blocks",
            "filename", "initial_comment", "filepath", "content_base64",
        },
        "salesforce": {
            "access_token", "instance_url", "refresh_token", "client_id",
            "client_secret", "record_id", "fields",
        },
        "stripe": {
            "api_key", "metadata", "idempotency_key", "amount", "currency", "source",
            "customer_id", "description", "payment_method", "confirm", "price_id",
            "payment_behavior", "default_payment_method", "card_token",
            "subscription_id", "cancel_at_period_end", "charge_id",
            "payment_intent_id", "reason",
        },
        "postgres_v2": {"database_connection_str", "schema", "table_name"},
    }

    for descriptor in M8FLOW_DESCRIPTORS:
        allowed = accepted[descriptor["id"]]
        declared = {field["id"] for field in descriptor["profileFields"]} | {
            field["id"] for field in descriptor["taskFields"]
        }
        assert declared <= allowed, (descriptor["id"], sorted(declared - allowed))


def test_profile_and_task_fields_never_overlap() -> None:
    """A field on both would be filled from the profile and by the task."""
    from m8flow_backend.connectors.m8flow_templates import M8FLOW_DESCRIPTORS

    for descriptor in M8FLOW_DESCRIPTORS:
        profile_ids = {field["id"] for field in descriptor["profileFields"]}
        task_ids = {field["id"] for field in descriptor["taskFields"]}
        assert not (profile_ids & task_ids), descriptor["id"]


def test_credentials_are_marked_secret_so_they_are_never_returned() -> None:
    from m8flow_backend.connectors.m8flow_templates import M8FLOW_DESCRIPTORS

    for descriptor in M8FLOW_DESCRIPTORS:
        for field in descriptor["profileFields"]:
            assert field["secret"] is True, (descriptor["id"], field["id"])
            assert field["binding"] == "secret_param", (descriptor["id"], field["id"])
