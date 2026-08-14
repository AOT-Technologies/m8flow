"""SMTP connector.

Field names mirror ``SendHTMLEmail.__init__`` in the m8flow SMTP connector.
Message fields (email_to/subject/body/...) stay with the service task.
"""

from __future__ import annotations

from m8flow_backend.connectors.base import (
    BOOLEAN,
    DEFAULT_GROUPS,
    SELECT,
    Choice,
    ConnectorDefinition,
    config_param,
    secret_param,
)
from m8flow_backend.connectors.registry import register


@register
class SmtpConnector(ConnectorDefinition):
    connector_type = "smtp"
    display_name = "SMTP"
    description = "Send emails through SMTP"
    category = "messaging"
    icon = "email"
    docs_anchor = "#smtp-connector"
    groups = DEFAULT_GROUPS
    test_operation = "smtp/SendHTMLEmail"

    fields = (
        config_param(
            "smtp_host",
            "SMTP Host",
            example="smtp.gmail.com",
        ),
        config_param(
            "smtp_port",
            "SMTP Port",
            type=SELECT,
            default=587,
            choices=(
                Choice(value=25, label="25 (Unencrypted)"),
                Choice(value=587, label="587 (STARTTLS)"),
                Choice(value=465, label="465 (SSL/TLS)"),
            ),
        ),
        config_param(
            "smtp_starttls",
            "Use STARTTLS",
            type=BOOLEAN,
            required=False,
            default=True,
        ),
        config_param(
            "email_from",
            "Default From Address",
            required=False,
            format="email",
            help_text="Used when the service task leaves email_from empty.",
        ),
        secret_param(
            "smtp_user",
            "Username",
            required=False,
            is_highly_sensitive=False,
        ),
        secret_param(
            "smtp_password",
            "Password",
            required=False,
            help_text="Leave both username and password empty for an unauthenticated relay.",
        ),
    )
