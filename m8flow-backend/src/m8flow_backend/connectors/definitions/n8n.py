"""n8n connector: trigger workflows and query the Public API.

Two integration styles with disjoint credentials: TriggerWorkflow calls a
webhook URL and needs no API key, while the four API operators need base_url +
api_key. Both sets live in one profile; the runtime patch injects only what the
chosen operator actually declares, so the webhook operator never receives an
api_key it would reject.

Names verified against m8flow-connector-proxy/README.md.
"""

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
class N8nConnector(ConnectorDefinition):
    id: ClassVar[str] = "m8flow.n8n.v1"
    connector_type: ClassVar[str] = "n8n"
    display_name: ClassVar[str] = "n8n"
    description: ClassVar[str] = "Trigger n8n workflows and query executions"
    category: ClassVar[str] = "automation"
    icon: ClassVar[str] = "extension"
    docs_anchor: ClassVar[str] = "n8n-connector"
    groups: ClassVar[tuple[dict[str, str], ...]] = (
        {"id": "connection", "label": "Connection"},
        {"id": "authentication", "label": "Authentication"},
    )

    base_url: Annotated[str | None, config_param(
        "connection", label="Instance URL", format="url",
        example="http://host.docker.internal:5678",
        help_text="Must be reachable from the connector proxy, not the browser.")]
    api_key: Annotated[str | None, secret_param(
        "authentication", label="Public API Key",
        help_text="Settings > n8n API. Not needed for webhook triggers.")]
    auth_header_value: Annotated[str | None, secret_param(
        "authentication", label="Webhook Auth Header Value",
        help_text="Used when a webhook node is set to header auth.")]
    password: Annotated[str | None, secret_param(
        "authentication", label="Webhook Basic Auth Password",
        help_text="Used when a webhook node is set to basic auth.")]

    webhook_url: Annotated[str | None, task_param(label="Webhook URL")]
    method: Annotated[str | None, task_param(label="HTTP Method")]
    payload: Annotated[str | None, task_param(label="Payload (JSON)", widget="textarea")]
    auth_type: Annotated[str | None, task_param(label="Auth Type")]
    auth_header_name: Annotated[str | None, task_param(label="Auth Header Name")]
    username: Annotated[str | None, task_param(label="Basic Auth Username")]
    workflow_id: Annotated[str | None, task_param(label="Workflow ID")]
    execution_id: Annotated[str | None, task_param(label="Execution ID")]
    status: Annotated[str | None, task_param(label="Status")]
    active: Annotated[str | None, task_param(label="Active")]
    limit: Annotated[int | None, task_param(label="Limit", type="number")]
    cursor: Annotated[str | None, task_param(label="Cursor")]
    include_data: Annotated[bool | None, task_param(label="Include Data", type="boolean")]
