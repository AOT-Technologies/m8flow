"""Salesforce connector: Lead and Contact CRUD.

Names verified against the "salesforce-lead-creation-with-slack-notification"
sample template. Supplying refresh_token + client_id + client_secret alongside
the access token lets the connector self-refresh on a 401, so all five live in
the profile.
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    secret_param,
    task_param,
)
from m8flow_backend.connectors.registry import register


@register
class SalesforceConnector(ConnectorDefinition):
    id: ClassVar[str] = "m8flow.salesforce.v1"
    connector_type: ClassVar[str] = "salesforce"
    display_name: ClassVar[str] = "Salesforce"
    description: ClassVar[str] = "Manage Salesforce leads and contacts"
    category: ClassVar[str] = "crm"
    icon: ClassVar[str] = "cloud"
    docs_anchor: ClassVar[str] = "salesforce-connector"
    groups: ClassVar[tuple[dict[str, str], ...]] = (
        {"id": "connection", "label": "Connection"},
        {"id": "authentication", "label": "Authentication"},
    )

    instance_url: Annotated[str, secret_param(
        "connection", label="Instance URL", widget="text",
        example="https://mycompany.my.salesforce.com")]
    access_token: Annotated[str, secret_param(
        "authentication", label="Access Token")]
    refresh_token: Annotated[str | None, secret_param(
        "authentication", label="Refresh Token",
        help_text="With client id + secret, enables automatic token refresh.")]
    client_id: Annotated[str | None, secret_param(
        "authentication", label="Consumer Key", widget="text")]
    client_secret: Annotated[str | None, secret_param(
        "authentication", label="Consumer Secret")]

    record_id: Annotated[str | None, task_param(label="Record ID")]
    fields: Annotated[str | None, task_param(
        label="Fields (JSON string)", widget="textarea")]
