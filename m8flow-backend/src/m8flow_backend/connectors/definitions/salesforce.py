"""Salesforce connector.

The three refresh fields are optional as a set: the connector only attempts a
token refresh when refresh_token, client_id and client_secret are all present.
"""

from __future__ import annotations

from m8flow_backend.connectors.base import (
    DEFAULT_GROUPS,
    ConnectorDefinition,
    config_param,
    secret_param,
)
from m8flow_backend.connectors.registry import register


@register
class SalesforceConnector(ConnectorDefinition):
    connector_type = "salesforce"
    display_name = "Salesforce"
    description = "Manage Salesforce leads and contacts"
    category = "crm"
    icon = "cloud"
    docs_anchor = "#salesforce-connector"
    groups = DEFAULT_GROUPS

    fields = (
        config_param(
            "instance_url",
            "Instance URL",
            format="url",
            example="https://yourorg.my.salesforce.com",
        ),
        config_param(
            "client_id",
            "Client ID",
            group="authentication",
            required=False,
            help_text="Connected App consumer key. Needed only for token refresh.",
        ),
        secret_param("access_token", "Access Token"),
        secret_param(
            "client_secret",
            "Client Secret",
            required=False,
        ),
        secret_param(
            "refresh_token",
            "Refresh Token",
            required=False,
            help_text="Supply with Client ID and Client Secret to auto-refresh expired tokens.",
        ),
    )
