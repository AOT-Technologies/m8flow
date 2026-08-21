"""HTTP connector: outbound REST calls.

Only optional basic-auth credentials are worth saving in a profile; the URL and
payload belong to the task. Names verified against
m8flow-connector-proxy/README.md.
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
class HttpConnector(ConnectorDefinition):
    id: ClassVar[str] = "m8flow.http.v1"
    connector_type: ClassVar[str] = "http"
    display_name: ClassVar[str] = "HTTP"
    description: ClassVar[str] = "Make REST API calls from workflows"
    category: ClassVar[str] = "integration"
    icon: ClassVar[str] = "globe"
    docs_anchor: ClassVar[str] = "http-connector"
    groups: ClassVar[tuple[dict[str, str], ...]] = (
        {"id": "authentication", "label": "Authentication"},
    )

    basic_auth_username: Annotated[str | None, secret_param(
        "authentication", label="Basic Auth Username", is_highly_sensitive=False)]
    basic_auth_password: Annotated[str | None, secret_param(
        "authentication", label="Basic Auth Password")]

    url: Annotated[str, task_param(label="URL", example="https://api.example.com/v1/items")]
    headers: Annotated[str | None, task_param(label="Headers (JSON)", widget="textarea")]
    params: Annotated[str | None, task_param(label="Query Params (JSON)", widget="textarea")]
    data: Annotated[str | None, task_param(label="Body (JSON)", widget="textarea")]
