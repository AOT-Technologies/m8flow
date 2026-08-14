"""GitHub connector.

``owner`` and ``repo`` stay service-task parameters: a single token normally
spans several repositories, so pinning them to the profile would force one
profile per repository.
"""

from __future__ import annotations

from m8flow_backend.connectors.base import (
    ConnectorDefinition,
    FieldGroup,
    secret_param,
)
from m8flow_backend.connectors.registry import register


@register
class GithubConnector(ConnectorDefinition):
    connector_type = "github"
    display_name = "GitHub"
    description = "Work with GitHub repositories, branches, and pull requests"
    category = "development"
    icon = "code"
    docs_anchor = "#github-connector"
    groups = (FieldGroup(id="authentication", label="Authentication"),)
    test_operation = "github/ConnectRepository"

    fields = (
        secret_param(
            "token",
            "Personal Access Token",
            help_text="Classic PAT or fine-grained token with repo scope.",
        ),
    )
