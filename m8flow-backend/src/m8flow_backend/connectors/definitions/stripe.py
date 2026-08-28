"""Stripe connector: payments, charges and subscriptions."""

from __future__ import annotations

from typing import Annotated, ClassVar

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    secret_param,
    task_param,
)
from m8flow_backend.connectors.registry import register


@register
class StripeConnector(ConnectorDefinition):
    id: ClassVar[str] = "m8flow.stripe.v1"
    connector_type: ClassVar[str] = "stripe"
    display_name: ClassVar[str] = "Stripe"
    description: ClassVar[str] = "Create payments, subscriptions, charges, and refunds"
    category: ClassVar[str] = "payment"
    icon: ClassVar[str] = "payment"
    docs_anchor: ClassVar[str] = "stripe-connector"
    groups: ClassVar[tuple[dict[str, str], ...]] = (
        {"id": "authentication", "label": "Authentication"},
    )

    api_key: Annotated[str, secret_param(
        "authentication", label="Secret Key",
        help_text="Stripe secret key, sk_test_... or sk_live_...")]

    amount: Annotated[int | None, task_param(
        label="Amount", type="number",
        help_text="In the currency's smallest unit: 1000 = $10.00.")]
    currency: Annotated[str | None, task_param(label="Currency", example="usd")]
    source: Annotated[str | None, task_param(label="Source", example="tok_visa")]
    customer_id: Annotated[str | None, task_param(label="Customer ID")]
    price_id: Annotated[str | None, task_param(label="Price ID")]
    subscription_id: Annotated[str | None, task_param(label="Subscription ID")]
    idempotency_key: Annotated[str | None, task_param(label="Idempotency Key")]
