"""Stripe connector."""

from __future__ import annotations

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    FieldGroup,
    secret_param,
)
from m8flow_backend.connectors.registry import register


@register
class StripeConnector(ConnectorDefinition):
    connector_type = "stripe"
    display_name = "Stripe"
    description = "Create payments, subscriptions, charges, and refunds"
    category = "payments"
    icon = "payment"
    docs_anchor = "#stripe-connector"
    groups = (FieldGroup(id="authentication", label="Authentication"),)

    fields = (
        secret_param(
            "api_key",
            "API Key",
            help_text="Use a restricted key where possible; test keys start with sk_test_.",
        ),
    )
