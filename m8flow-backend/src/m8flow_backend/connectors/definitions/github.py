"""GitHub connector: repositories, branches and pull requests.

UNVERIFIED FIELD NAMES. Unlike the other definitions, the GitHub connector has
no section in m8flow-connector-proxy/README.md and no sample template uses it,
so the proxy's real keyword arguments could not be confirmed offline. The names
below are the best inference from the connector's description.

This is safe but incomplete: the runtime patch injects a profile value only
into parameters the operator actually declares (from GET /v1/commands), so a
wrong name here is inert rather than fatal -- the value is simply not sent, and
`bin/check-connector-fields.py` reports the mismatch. Confirm against a running
proxy and correct before relying on GitHub profiles.
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
class GithubConnector(ConnectorDefinition):
    id: ClassVar[str] = "m8flow.github.v1"
    connector_type: ClassVar[str] = "github"
    display_name: ClassVar[str] = "GitHub"
    description: ClassVar[str] = "Work with GitHub repositories, branches, and pull requests"
    category: ClassVar[str] = "devtools"
    icon: ClassVar[str] = "code"
    groups: ClassVar[tuple[dict[str, str], ...]] = (
        {"id": "authentication", "label": "Authentication"},
        {"id": "repository", "label": "Repository"},
    )

    auth_token: Annotated[str, secret_param(
        "authentication", label="Personal Access Token",
        help_text="A PAT with the scopes the chosen operations need.")]

    repo_owner: Annotated[str | None, task_param(label="Repository Owner")]
    repo_name: Annotated[str | None, task_param(label="Repository Name")]
