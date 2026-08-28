"""Slack connector: post messages, DMs and file uploads."""

from __future__ import annotations

from typing import Annotated, ClassVar

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    config_param,
    secret_param,
    task_param,
)
from m8flow_backend.connectors.registry import register


@register
class SlackConnector(ConnectorDefinition):
    id: ClassVar[str] = "m8flow.slack.v1"
    connector_type: ClassVar[str] = "slack"
    display_name: ClassVar[str] = "Slack"
    description: ClassVar[str] = "Send messages and notifications"
    category: ClassVar[str] = "messaging"
    icon: ClassVar[str] = "chat"
    docs_anchor: ClassVar[str] = "slack-connector"
    groups: ClassVar[tuple[dict[str, str], ...]] = (
        {"id": "authentication", "label": "Authentication"},
        {"id": "message", "label": "Message"},
    )

    token: Annotated[str, secret_param(
        "authentication", label="Bot Token",
        help_text="Bot User OAuth token, starts with xoxb-.")]
    channel: Annotated[str | None, config_param(
        "message", label="Default Channel", example="#general",
        help_text="Used when a task does not name one.")]

    message: Annotated[str | None, task_param(label="Message", widget="textarea")]
    user_id: Annotated[str | None, task_param(label="User ID", example="U01234ABCD")]
    blocks: Annotated[str | None, task_param(label="Blocks (Block Kit JSON)", widget="textarea")]
    filepath: Annotated[str | None, task_param(label="File Path")]
    content_base64: Annotated[str | None, task_param(label="File Content (base64)")]
