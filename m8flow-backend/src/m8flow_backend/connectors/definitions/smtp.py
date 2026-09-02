"""SMTP connector: send email.

Parameter names match the shipped m8flow-connector-smtp package (verified
against the "Expense Claim with DMN and SMTP Connector" sample template).
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    config_param,
    secret_param,
    task_param,
)
from m8flow_backend.connectors.registry import register


@register
class SmtpConnector(ConnectorDefinition):
    id: ClassVar[str] = "m8flow.smtp.v1"
    connector_type: ClassVar[str] = "smtp"
    display_name: ClassVar[str] = "SMTP"
    description: ClassVar[str] = "Send emails through SMTP"
    category: ClassVar[str] = "messaging"
    icon: ClassVar[str] = "email"
    docs_anchor: ClassVar[str] = "smtp-connector"
    groups: ClassVar[tuple[dict[str, str], ...]] = (
        {"id": "connection", "label": "Connection"},
        {"id": "authentication", "label": "Authentication"},
        {"id": "message", "label": "Message"},
    )

    # --- profile: connection -------------------------------------------------
    smtp_host: Annotated[str, config_param(
        "connection", label="SMTP Host", example="smtp.gmail.com")]
    smtp_port: Annotated[Literal[25, 587, 465], config_param(
        "connection", label="SMTP Port", default_value=587,
        choices=[{"value": 25, "label": "25 (Unencrypted)"},
                 {"value": 587, "label": "587 (STARTTLS)"},
                 {"value": 465, "label": "465 (SSL/TLS)"}])]
    smtp_starttls: Annotated[bool | None, config_param(
        "connection", label="Use STARTTLS", default_value=True,
        help_text="Enforce STARTTLS. Usually on for port 587.")]
    email_from: Annotated[str | None, config_param(
        "message", label="From Address", format="email",
        help_text="Default sender. A task may override it.")]

    # --- profile: authentication ---------------------------------------------
    smtp_user: Annotated[str | None, secret_param(
        "authentication", label="Username", widget="text")]
    smtp_password: Annotated[str | None, secret_param(
        "authentication", label="Password")]

    # --- runtime: the service task supplies these ----------------------------
    email_to: Annotated[str, task_param(label="To", example="user@example.com")]
    email_subject: Annotated[str, task_param(label="Subject")]
    email_body: Annotated[str | None, task_param(label="Body", widget="textarea")]
    email_body_html: Annotated[str | None, task_param(label="HTML Body", widget="textarea")]
    email_cc: Annotated[str | None, task_param(label="CC")]
    email_bcc: Annotated[str | None, task_param(label="BCC")]
    email_reply_to: Annotated[str | None, task_param(label="Reply-To")]
    attachments: Annotated[str | None, task_param(label="Attachments")]
