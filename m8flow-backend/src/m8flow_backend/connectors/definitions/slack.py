"""Slack connector.

Only the bot token belongs to the profile. ``channel`` stays a service-task
parameter: one workspace token routinely posts to many channels, so binding a
channel to the credential set would take that choice away from the author.
"""

from __future__ import annotations

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    FieldGroup,
    secret_param,
)
from m8flow_backend.connectors.registry import register


@register
class SlackConnector(ConnectorDefinition):
    connector_type = "slack"
    display_name = "Slack"
    description = "Send messages and notifications"
    category = "messaging"
    icon = "chat"
    docs_anchor = "#slack-connector"
    groups = (FieldGroup(id="authentication", label="Authentication"),)
    test_operation = "slack/PostMessage"

    fields = (
        secret_param(
            "token",
            "Bot Token",
            help_text="Slack bot token, starts with xoxb-.",
        ),
    )
