"""HTTP connector.

Declared so the connector carries display metadata, but it has no profile
fields: every HTTP operation takes its URL, headers and any auth inline on the
service task, and there is no credential set to reuse across tasks. With no
profile fields the modeler hides the profile dropdown for this connector.
"""

from __future__ import annotations

from m8flow_backend.connectors.base import ConnectorDefinition
from m8flow_backend.connectors.registry import register


@register
class HttpConnector(ConnectorDefinition):
    connector_type = "http"
    display_name = "HTTP"
    description = "Make REST API calls from workflows"
    category = "integration"
    icon = "globe"
    docs_anchor = "#http-connector"
    groups = ()
    fields = ()
