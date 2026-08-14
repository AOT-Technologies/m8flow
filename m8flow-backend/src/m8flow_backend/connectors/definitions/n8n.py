"""n8n connector.

base_url + api_key cover the REST operations (ListWorkflows, GetWorkflow,
ListExecutions, GetExecution). TriggerWorkflow authenticates per webhook
instead, so its auth parameters stay with the service task.
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
class N8nConnector(ConnectorDefinition):
    connector_type = "n8n"
    display_name = "n8n"
    description = "Trigger and inspect n8n workflows"
    category = "automation"
    icon = "extension"
    docs_anchor = "#n8n-connector"
    groups = DEFAULT_GROUPS
    test_operation = "n8n/ListWorkflows"

    fields = (
        config_param(
            "base_url",
            "Instance URL",
            format="url",
            example="https://your-instance.app.n8n.cloud",
        ),
        secret_param(
            "api_key",
            "API Key",
            help_text="Sent as the X-N8N-API-KEY header.",
        ),
    )
